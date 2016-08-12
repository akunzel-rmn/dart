from dart.context.locator import injectable
from dart.message.call import TriggerCall
from dart.trigger.subscription import subscription_batch_trigger
from dart.trigger.workflow import workflow_completion_trigger, workflow_failure_trigger
from dart.trigger.super import super_trigger


@injectable
class TriggerProxy(object):
    def __init__(self, trigger_broker):
        self._trigger_broker = trigger_broker

    def process_trigger(self, trigger_type, message):
        """ :type trigger_type: dart.model.trigger.TriggerType
            :type message: dict """
        args = {'call': TriggerCall.PROCESS_TRIGGER, 'trigger_type_name': trigger_type.name, 'message': message}
        self._trigger_broker.send_message(args)

    def try_next_action(self, datastore_id):
        args = {'call': TriggerCall.TRY_NEXT_ACTION, 'datastore_id': datastore_id}
        self._trigger_broker.send_message(args)

    def complete_action(self, action_id, action_state, error_message):
        args = {'call': TriggerCall.COMPLETE_ACTION, 'action_id': action_id, 'action_state': action_state,
                'error_message': error_message}
        self._trigger_broker.send_message(args)

    def trigger_workflow_completion(self, workflow_id):
        self.process_trigger(workflow_completion_trigger, {'workflow_id': workflow_id})

    def trigger_workflow_failure(self, workflow_id):
        self.process_trigger(workflow_failure_trigger, {'workflow_id': workflow_id})

    def trigger_subscription_evaluation(self, trigger_id):
        self.process_trigger(subscription_batch_trigger, {'trigger_id': trigger_id})

    def super_trigger_evaluation(self, trigger_id):
        self.process_trigger(super_trigger, {'trigger_id': trigger_id})
