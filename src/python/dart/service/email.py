import logging
from mailer import Mailer, Message
from retrying import retry
from dart.context.locator import injectable
from dart.util.config import _get_dart_host


_logger = logging.getLogger(__name__)


@injectable
class Emailer(object):
    def __init__(self, dart_config):
        email_config = dart_config['email']
        self._env_name = dart_config['dart']['env_name'].upper()
        self._mailer = Mailer(**email_config['mailer'])
        self._from = email_config['from']
        self._cc_on_error = email_config['cc_on_error']
        self._debug = email_config.get('debug', False)
        self._suppress_send = email_config.get('suppress_send', False)
        self._dart_host = _get_dart_host(dart_config)

    def get_entity_link(self, entity, action_id):
        return 'http://%s/entities/%s?f=["id=%s"]' % (self._dart_host, entity, action_id)

    def get_workflow_manager_link(self, workflow_id):
        return 'http://%s/#/managers/workflow?id=%s&t=wf' % (self._dart_host, workflow_id)

    # we experience occasional gmail API issues, so we will retry a few times
    @retry(wait_fixed=10000, stop_max_attempt_number=12)
    def send_email(self, subject, body, to, cc=None):
        msg = Message(From=self._from, To=to, Subject=self._env_name + ' - ' + subject, Body=body, CC=cc)
        if self._suppress_send:
            _logger.info('email suppressed: subject=%s' % msg.Subject)
            return
        self._mailer.send(msg, self._debug)

    def send_error_email(self, subject, body, to=None):
        cc = None
        if to:
            cc = self._cc_on_error
        else:
            to = self._cc_on_error
        self.send_email(subject, body, to, cc=cc)

    def send_action_failed_email(self, action, datastore):
        values = (action.id, action.data.action_type_name, datastore.id, datastore.data.name,
                  self.get_entity_link('actions', action.id), action.data.error_message)
        self.send_error_email(
            'FAILED Dart: action (id=%s, name=%s)' % (action.id, action.data.action_type_name),
            'action (id=%s, name=%s) FAILED for datastore (id=%s, name=%s)\n\n%s\n\n%s' % values,
            action.data.on_failure_email
        )

    def send_action_completed_email(self, action, datastore):
        values = (action.id, action.data.action_type_name, datastore.id, datastore.data.name,
                  self.get_entity_link('actions', action.id))
        self.send_email(
            'COMPLETED Dart: action (id=%s, name=%s)' % (action.id, action.data.action_type_name),
            'action (id=%s, name=%s) COMPLETED for datastore (id=%s, name=%s)\n\n%s' % values,
            action.data.on_success_email
        )

    def send_workflow_failed_email(self, workflow, wf_instance):
        values = (workflow.id, workflow.data.name, wf_instance.id, self.get_workflow_manager_link(workflow.id),
                  wf_instance.data.error_message)
        self.send_error_email(
            'FAILED Dart: workflow (id=%s, name=%s)' % (workflow.id, workflow.data.name),
            'workflow (id=%s, name=%s) FAILED for instance (id=%s)\n\n%s\n\n%s' % values,
            workflow.data.on_failure_email
        )

    def send_workflow_completed_email(self, workflow, wf_instance):
        values = (workflow.id, workflow.data.name, wf_instance.id, self.get_workflow_manager_link(workflow.id))
        self.send_email(
            'COMPLETED Dart: workflow (id=%s, name=%s)' % (workflow.id, workflow.data.name),
            'workflow (id=%s, name=%s) COMPLETED for instance (id=%s)\n\n%s' % values,
            workflow.data.on_success_email
        )

    def send_workflow_started_email(self, workflow, wf_instance):
        values = (workflow.id, workflow.data.name, wf_instance.id, self.get_workflow_manager_link(workflow.id))
        self.send_email(
            'STARTED Dart: workflow (id=%s, name=%s)' % (workflow.id, workflow.data.name),
            'workflow (id=%s, name=%s) has STARTED: instance (id=%s)\n\n%s' % values,
            workflow.data.on_started_email
        )

    def send_subscription_failed_email(self, subscription):
        values = (subscription.id, subscription.data.name, self.get_entity_link('subscriptions', subscription.id))
        self.send_error_email(
            'FAILED Dart: subscription (id=%s, name=%s)' % (subscription.id, subscription.data.name),
            'subscription (id=%s, name=%s) FAILED\n\n%s' % values,
            subscription.data.on_failure_email
        )

    def send_subscription_completed_email(self, subscription):
        values = (subscription.id, subscription.data.name, self.get_entity_link('subscriptions', subscription.id))
        self.send_email(
            'COMPLETED Dart: subscription (id=%s, name=%s)' % (subscription.id, subscription.data.name),
            'subscription (id=%s, name=%s) COMPLETED\n\n%s' % values,
            subscription.data.on_success_email
        )
