from datetime import datetime
import logging
from sqlalchemy import DateTime, desc
from dart.context.locator import injectable
from dart.model.action import ActionState
from dart.model.datastore import DatastoreState
from dart.model.orm import WorkflowDao, WorkflowInstanceDao
from dart.context.database import db
from dart.model.subscription import SubscriptionElementState
from dart.model.workflow import WorkflowState, WorkflowInstanceState, WorkflowInstanceData
from dart.schema.base import default_and_validate
from dart.schema.workflow import workflow_schema, workflow_instance_schema
from dart.service.patcher import patch_difference, retry_stale_data
from dart.util.rand import random_id


_logger = logging.getLogger(__name__)


@injectable
class WorkflowService(object):
    def __init__(self, datastore_service, action_service, trigger_proxy, filter_service, subscription_service,
                 subscription_element_service, emailer):
        self._datastore_service = datastore_service
        self._action_service = action_service
        self._trigger_proxy = trigger_proxy
        self._filter_service = filter_service
        self._subscription_service = subscription_service
        self._subscription_element_service = subscription_element_service
        self._emailer = emailer

    @staticmethod
    def save_workflow(workflow, commit=True, flush=False):
        """ :type workflow: dart.model.workflow.Workflow """
        workflow = default_and_validate(workflow, workflow_schema())

        workflow_dao = WorkflowDao()
        workflow_dao.id = random_id()
        workflow_dao.data = workflow.data.to_dict()
        db.session.add(workflow_dao)
        if flush:
            db.session.flush()
        if commit:
            db.session.commit()
        workflow = workflow_dao.to_model()
        return workflow

    @staticmethod
    def save_workflow_instance(workflow, trigger_type, trigger_id, state):
        """ :type workflow: dart.model.workflow.Workflow
            :type trigger_type: dart.model.trigger.TriggerType """
        wf_instance_dao = WorkflowInstanceDao()
        wf_instance_dao.id = random_id()
        wf_data = workflow.data
        data = WorkflowInstanceData(
            workflow_id=workflow.id,
            engine_name=wf_data.engine_name,
            state=state,
            trigger_type=trigger_type.name,
            trigger_id=trigger_id,
            queued_time=datetime.now(),
            tags=wf_data.tags,
        )
        wf_instance_dao.data = data.to_dict()
        db.session.add(wf_instance_dao)
        db.session.commit()
        return wf_instance_dao.to_model()

    @staticmethod
    def get_workflow(workflow_id, raise_when_missing=True):
        """ :rtype: dart.model.workflow.Workflow """
        workflow_dao = WorkflowDao.query.get(workflow_id)
        if not workflow_dao and raise_when_missing:
            raise Exception('workflow with id=%s not found' % workflow_id)
        return workflow_dao.to_model() if workflow_dao else None

    def find_workflows(self, limit=20, offset=0):
        query = self.find_workflow_query()
        query = query.limit(limit).offset(offset)
        return [dao.to_model() for dao in query.all()]

    def find_workflows_count(self):
        return self.find_workflow_query().count()

    @staticmethod
    def find_workflow_query():
        return WorkflowDao.query.order_by(WorkflowDao.data['name'])

    @staticmethod
    def get_workflow_instance(workflow_instance_id, raise_when_missing=True):
        workflow_instance_dao = WorkflowInstanceDao.query.get(workflow_instance_id)
        if not workflow_instance_dao and raise_when_missing:
            raise Exception('workflow_instance_id with id=%s not found' % workflow_instance_id)
        return workflow_instance_dao.to_model() if workflow_instance_dao else None

    def find_workflow_instances(self, workflow_id=None, limit=None, offset=None):
        return [i.to_model() for i in self.find_workflow_instances_query(workflow_id, None, limit, offset).all()]

    def find_workflow_instances_count(self, workflow_id, states=None):
        return self.find_workflow_instances_query(workflow_id, states).count()

    @staticmethod
    def find_workflow_instances_query(workflow_id, states=None, limit=None, offset=None):
        query = WorkflowInstanceDao.query
        query = query.filter(WorkflowInstanceDao.data['workflow_id'].astext == workflow_id) if workflow_id else query
        query = query.filter(WorkflowInstanceDao.data['state'].astext.in_(states)) if states else query
        query = query.order_by(desc(WorkflowInstanceDao.data['start_time'].cast(DateTime)))
        query = query.limit(limit) if limit else query
        query = query.offset(offset) if offset else query
        return query

    def query_workflows(self, filters, limit=20, offset=0):
        """ :type filters: list[dart.model.query.Filter] """
        query = self._query_workflow_query(filters)
        query = query.limit(limit).offset(offset)
        return [w.to_model() for w in query.all()]

    def query_workflows_count(self, filters):
        """ :type filters: list[dart.model.query.Filter] """
        query = self._query_workflow_query(filters)
        return query.count()

    def _query_workflow_query(self, filters):
        query = WorkflowDao.query.order_by(desc(WorkflowDao.updated))
        for f in filters:
            query = self._filter_service.apply_filter(f, query, WorkflowDao, [workflow_schema()])
        return query

    def query_workflow_instances(self, filters, limit=20, offset=0):
        """ :type filters: list[dart.model.query.Filter] """
        query = self._query_workflow_instance_query(filters)
        query = query.limit(limit).offset(offset)
        return [w.to_model() for w in query.all()]

    def query_workflow_instances_count(self, filters):
        """ :type filters: list[dart.model.query.Filter] """
        query = self._query_workflow_instance_query(filters)
        return query.count()

    def _query_workflow_instance_query(self, filters):
        query = WorkflowInstanceDao.query.order_by(desc(WorkflowInstanceDao.updated))
        for f in filters:
            query = self._filter_service.apply_filter(f, query, WorkflowInstanceDao, [workflow_instance_schema()])
        return query

    def action_checkout(self, action):
        action = self._action_service.update_action_state(action, ActionState.RUNNING, action.data.error_message)
        if action.data.workflow_instance_id and action.data.first_in_workflow:
            wf_instance = self.get_workflow_instance(action.data.workflow_instance_id)
            self.update_workflow_instance_state(wf_instance, WorkflowInstanceState.RUNNING)
            wf = self.get_workflow(action.data.workflow_id)
            if wf.data.on_started_email:
                self._emailer.send_workflow_started_email(wf, wf_instance)
        return action

    def action_checkin(self, action, action_state, consume_subscription_state=None):
        """ :type action: dart.model.action.Action """
        if action.data.action_type_name == 'consume_subscription':
            action_based = SubscriptionElementState.CONSUMED if action_state == ActionState.COMPLETED\
                else SubscriptionElementState.UNCONSUMED
            state = consume_subscription_state or action_based
            self._subscription_element_service.update_subscription_elements_state(action.id, state)
        return self._action_service.update_action_state(action, ActionState.FINISHING, action.data.error_message)

    @staticmethod
    def patch_workflow(source_workflow, workflow):
        workflow = patch_difference(WorkflowDao, source_workflow, workflow)
        return workflow

    @staticmethod
    def default_and_validate_workflow(workflow):
        return default_and_validate(workflow, workflow_schema())

    @staticmethod
    def update_workflow_state(workflow, state):
        source_workflow = workflow.copy()
        workflow.data.state = state
        return patch_difference(WorkflowDao, source_workflow, workflow)

    @staticmethod
    def update_workflow_instance(workflow_instance, datastore_id):
        """ :type workflow_instance: dart.model.workflow.WorkflowInstance """
        source_workflow_instance = workflow_instance.copy()
        workflow_instance.data.datastore_id = datastore_id
        return patch_difference(WorkflowInstanceDao, source_workflow_instance, workflow_instance)

    @staticmethod
    @retry_stale_data
    def delete_workflow(workflow_id):
        workflow_dao = WorkflowDao.query.get(workflow_id)
        db.session.delete(workflow_dao)
        db.session.commit()

    @retry_stale_data
    def delete_workflow_instances(self, workflow_id):
        # We delete with synchronize_session=False here to avoid sqlalchemy blowing up.  It basically means
        # sqlalchemy will not try to figure out which session objects to invalidate (which is fine since the
        # session will expire after the commit anyways)
        offset = 0
        while True:
            # Find all workflow instances
            workflow_instances = self.find_workflow_instances(workflow_id, 20, offset)
            if not workflow_instances:
                break
            # Iterate and delete all actions in each workflow instance
            for workflow_instance in workflow_instances:
                self._action_service.delete_actions_in_workflow_instance(workflow_instance.id)
            offset += 20
        WorkflowInstanceDao.query.filter(WorkflowInstanceDao.data['workflow_id'].astext == workflow_id).delete(False)
        db.session.commit()

    @staticmethod
    def update_workflow_instance_state(workflow_instance, state, commit_changes=True, error_message=None):
        """ :type workflow_instance: dart.model.workflow.WorkflowInstance """
        source_workflow_instance = workflow_instance.copy()
        workflow_instance.data.state = state
        if state == WorkflowInstanceState.QUEUED:
            workflow_instance.data.queued_time = datetime.now()
        if state == WorkflowInstanceState.RUNNING:
            workflow_instance.data.start_time = datetime.now()
        elif state == WorkflowInstanceState.COMPLETED:
            workflow_instance.data.end_time = datetime.now()
        elif state == WorkflowInstanceState.FAILED:
            workflow_instance.data.end_time = datetime.now()
            workflow_instance.data.error_message = error_message
        return patch_difference(WorkflowInstanceDao, source_workflow_instance, workflow_instance, commit_changes)

    def run_triggered_workflow(self, workflow_id, trigger_type, trigger_id=None):
        wf = self.get_workflow(workflow_id, raise_when_missing=False)
        if not wf:
            _logger.info('workflow (id=%s) not found' % workflow_id)
            return
        if wf.data.state != WorkflowState.ACTIVE:
            _logger.info('expected workflow (id=%s) to be in ACTIVE state' % wf.id)
            return

        states = [WorkflowInstanceState.QUEUED, WorkflowInstanceState.RUNNING]
        if self.find_workflow_instances_count(wf.id, states) >= wf.data.concurrency:
            _logger.info('workflow (id=%s) has already reached max concurrency of %s' % (wf.id, wf.data.concurrency))
            return

        wf_instance = self.save_workflow_instance(wf, trigger_type, trigger_id, WorkflowInstanceState.QUEUED)

        datastore = self._datastore_service.get_datastore(wf.data.datastore_id, raise_when_missing=False)
        if not datastore:
            error_msg = 'the datastore (id=%s) defined for this workflow could not be found' % wf.data.datastore_id
            self.update_workflow_instance_state(wf_instance, WorkflowInstanceState.FAILED, error_message=error_msg)
            return

        if datastore.data.state == DatastoreState.TEMPLATE:
            datastore = self._datastore_service.clone_datastore(
                datastore,
                state=DatastoreState.ACTIVE,
                workflow_id=wf.id,
                workflow_instance_id=wf_instance.id,
                workflow_datastore_id=datastore.id,
            )
        if datastore.data.state != DatastoreState.ACTIVE:
            error_msg = 'expected datastore (id=%s) to be in ACTIVE state' % wf.id
            self.update_workflow_instance_state(wf_instance, WorkflowInstanceState.FAILED, error_message=error_msg)
            return

        wf_instance = self.update_workflow_instance(wf_instance, datastore.id)

        actions = self._action_service.find_actions(workflow_id=wf.id, states=[ActionState.TEMPLATE])
        if len(actions) <= 0:
            error_msg = 'no TEMPLATE actions were found for this workflow'
            self.update_workflow_instance_state(wf_instance, WorkflowInstanceState.FAILED, error_message=error_msg)
            return

        actions[0].data.first_in_workflow = True
        actions[-1].data.last_in_workflow = True

        self._action_service.clone_workflow_actions(
            source_actions=actions,
            target_datastore_id=datastore.id,
            datastore_id=datastore.id,
            workflow_id=wf.id,
            workflow_instance_id=wf_instance.id,
        )

        self._trigger_proxy.try_next_action(datastore.id)
