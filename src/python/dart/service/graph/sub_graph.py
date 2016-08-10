# coding=utf-8
from dart.model.action import Action, ActionState
from dart.model.action import ActionData
from dart.model.dataset import Dataset, DatasetData
from dart.model.datastore import DatastoreData, Datastore, DatastoreState
from dart.model.event import EventData, Event
from dart.model.graph import EntityType, Relationship, SubGraph, Ref
from dart.model.subscription import Subscription
from dart.model.subscription import SubscriptionData
from dart.model.trigger import Trigger, TriggerState
from dart.model.trigger import TriggerData
from dart.model.workflow import Workflow, WorkflowData, WorkflowState
from dart.trigger.event import event_trigger
from dart.trigger.scheduled import scheduled_trigger
from dart.trigger.subscription import subscription_batch_trigger
from dart.trigger.super import super_trigger
from dart.trigger.workflow import workflow_completion_trigger, workflow_failure_trigger


def get_static_subgraphs_by_engine_name_all_engines_related_none(engine_names, graph_entity_service):
    sub_graph_map = {}
    for engine_name in engine_names:
        entity_models = graph_entity_service.to_entity_models_with_randomized_ids([
            Datastore(id=Ref.datastore(1), data=DatastoreData(
                name='%s_datastore' % engine_name,
                engine_name=engine_name,
                state=DatastoreState.INACTIVE
            ))
        ])
        sub_graph_map[engine_name] = [
            SubGraph(
                name='datastore',
                description='create a new datastore entity',
                related_type=None,
                related_is_a=None,
                graph=graph_entity_service.to_graph(None, entity_models),
                entity_map=graph_entity_service.to_entity_map(entity_models),
                icon='⬟',
            )
        ]
    return sub_graph_map


def get_static_subgraphs_by_engine_name(engine, entity_type, graph_entity_service):
    if not engine:
        engineless_subgraphs = []
        for related_type, subgraph_list in _get_engineless_static_subgraphs_by_related_type(graph_entity_service).iteritems():
            if related_type == entity_type:
                engineless_subgraphs.extend(subgraph_list)
        return {None: engineless_subgraphs}

    if engine:
        engine_subgraphs = []
        engine_name = engine.data.name
        for related_type, subgraph_list in _get_static_subgraphs_by_related_type(engine, graph_entity_service).iteritems():
            if related_type == entity_type:
                engine_subgraphs.extend(subgraph_list)
        return {engine_name: engine_subgraphs}


def _get_engineless_static_subgraphs_by_related_type(graph_entity_service):
    sub_graph_map = {}

    d_entity_models = graph_entity_service.to_entity_models_with_randomized_ids(
        [Dataset(id=Ref.dataset(1), data=DatasetData(None, None, None, None, None, columns=[], partitions=[]))]
    )
    e_entity_models = graph_entity_service.to_entity_models_with_randomized_ids(
        [Event(id=Ref.event(1), data=EventData('event'))]
    )
    sub_graph_map[None] = [
        SubGraph(
            name='dataset',
            description='create a new dataset entity',
            related_type=None,
            related_is_a=None,
            graph=graph_entity_service.to_graph(None, d_entity_models),
            entity_map=graph_entity_service.to_entity_map(d_entity_models),
            icon='⬟',
        ),
        SubGraph(
            name='event',
            description='create a new event entity',
            related_type=None,
            related_is_a=None,
            graph=graph_entity_service.to_graph(None, e_entity_models),
            entity_map=graph_entity_service.to_entity_map(e_entity_models),
            icon='★',
        ),
    ]

    entity_models = graph_entity_service.to_entity_models_with_randomized_ids(
        [Subscription(id=Ref.subscription(1), data=SubscriptionData('subscription', Ref.parent()))]
    )
    sub_graph_map[EntityType.dataset] = [
        SubGraph(
            name='subscription',
            description='create a new subscription entity',
            related_type=EntityType.dataset,
            related_is_a=Relationship.PARENT,
            graph=graph_entity_service.to_graph(None, entity_models),
            entity_map=graph_entity_service.to_entity_map(entity_models),
            icon='⬢',
        ),
    ]

    entity_models = graph_entity_service.to_entity_models_with_randomized_ids([
        Trigger(id=Ref.trigger(1), data=TriggerData(
            name='%s_trigger' % event_trigger.name,
            trigger_type_name=event_trigger.name,
            state=TriggerState.INACTIVE,
            workflow_ids=[],
            args={'event_id': Ref.parent()}
        ))
    ])
    sub_graph_map[EntityType.event] = [
        SubGraph(
            name='event trigger',
            description='create a new event trigger entity',
            related_type=EntityType.event,
            related_is_a=Relationship.PARENT,
            graph=graph_entity_service.to_graph(None, entity_models),
            entity_map=graph_entity_service.to_entity_map(entity_models),
            icon='▼',
        ),
    ]

    entity_models = graph_entity_service.to_entity_models_with_randomized_ids([
        Trigger(id=Ref.trigger(1), data=TriggerData(
            name='%s_trigger' % subscription_batch_trigger.name,
            trigger_type_name=subscription_batch_trigger.name,
            state=TriggerState.INACTIVE,
            workflow_ids=[],
            args={'subscription_id': Ref.parent(), 'unconsumed_data_size_in_bytes': 1000000}
        ))
    ])
    sub_graph_map[EntityType.subscription] = [
        SubGraph(
            name='subscription batch trigger',
            description='create a new subscription batch trigger entity',
            related_type=EntityType.subscription,
            related_is_a=Relationship.PARENT,
            graph=graph_entity_service.to_graph(None, entity_models),
            entity_map=graph_entity_service.to_entity_map(entity_models),
            icon='▼',
        ),
    ]

    return sub_graph_map


def _get_static_subgraphs_by_related_type(engine, graph_entity_service):
    engine_name = engine.data.name
    sub_graph_map = {EntityType.workflow: []}

    for action_type in engine.data.supported_action_types:
        entity_models = graph_entity_service.to_entity_models_with_randomized_ids([
            Action(id=Ref.action(1), data=ActionData(
                name=action_type.name,
                action_type_name=action_type.name,
                engine_name=engine_name,
                workflow_id=Ref.parent(),
                state=ActionState.TEMPLATE,
                args={} if action_type.params_json_schema else None
            ))
        ])
        sub_graph_map[EntityType.workflow].append(
            SubGraph(
                name=action_type.name,
                description=action_type.description,
                related_type=EntityType.workflow,
                related_is_a=Relationship.PARENT,
                graph=graph_entity_service.to_graph(None, entity_models),
                entity_map=graph_entity_service.to_entity_map(entity_models),
                icon='●',
            )
        )

    entity_models = graph_entity_service.to_entity_models_with_randomized_ids([
        Trigger(id=Ref.trigger(1), data=TriggerData(
            name='%s_trigger' % workflow_completion_trigger.name,
            trigger_type_name=workflow_completion_trigger.name,
            state=TriggerState.INACTIVE,
            workflow_ids=[],
            args={'completed_workflow_id': Ref.parent()}
        ))
    ])
    sub_graph_map[EntityType.workflow].extend([
        SubGraph(
            name='workflow completion trigger',
            description='create a new workflow_completion trigger entity',
            related_type=EntityType.workflow,
            related_is_a=Relationship.PARENT,
            graph=graph_entity_service.to_graph(None, entity_models),
            entity_map=graph_entity_service.to_entity_map(entity_models),
            icon='▼',
        ),
    ])

    entity_models = graph_entity_service.to_entity_models_with_randomized_ids([
        Trigger(id=Ref.trigger(1), data=TriggerData(
            name='%s_trigger' % workflow_failure_trigger.name,
            trigger_type_name=workflow_failure_trigger.name,
            state=TriggerState.INACTIVE,
            workflow_ids=[],
            args={'failed_workflow_id': Ref.parent()}
        ))
    ])
    sub_graph_map[EntityType.workflow].extend([
        SubGraph(
            name='workflow failure trigger',
            description='create a new workflow_failure trigger entity',
            related_type=EntityType.workflow,
            related_is_a=Relationship.PARENT,
            graph=graph_entity_service.to_graph(None, entity_models),
            entity_map=graph_entity_service.to_entity_map(entity_models),
            icon='▼',
        ),
    ])

    entity_models = graph_entity_service.to_entity_models_with_randomized_ids([
        Trigger(id=Ref.trigger(1), data=TriggerData(
            name='%s_trigger' % scheduled_trigger.name,
            trigger_type_name=scheduled_trigger.name,
            state=TriggerState.INACTIVE,
            workflow_ids=[Ref.child()],
        ))
    ])
    sub_graph_map[EntityType.workflow].extend([
        SubGraph(
            name='scheduled trigger',
            description='create a new scheduled trigger entity',
            related_type=EntityType.workflow,
            related_is_a=Relationship.CHILD,
            graph=graph_entity_service.to_graph(None, entity_models),
            entity_map=graph_entity_service.to_entity_map(entity_models),
            icon='▼',
        ),
    ])

    entity_models = graph_entity_service.to_entity_models_with_randomized_ids([
        Trigger(id=Ref.trigger(1), data=TriggerData(
            name='%s_trigger' % super_trigger.name,
            trigger_type_name=super_trigger.name,
            state=TriggerState.INACTIVE,
            workflow_ids=[Ref.child()],
        ))
    ])
    sub_graph_map[EntityType.workflow].extend([
        SubGraph(
            name='super trigger',
            description='create a new super trigger entity',
            related_type=EntityType.workflow,
            related_is_a=Relationship.CHILD,
            graph=graph_entity_service.to_graph(None, entity_models),
            entity_map=graph_entity_service.to_entity_map(entity_models),
            icon='▼',
        ),
    ])

    entity_models = graph_entity_service.to_entity_models_with_randomized_ids([
        Workflow(id=Ref.workflow(1), data=WorkflowData(
            name='workflow',
            datastore_id=Ref.parent(),
            engine_name=engine_name,
            state=WorkflowState.INACTIVE
        ))
    ])
    sub_graph_map[EntityType.datastore] = [
        SubGraph(
            name='workflow',
            description='create a new workflow entity',
            related_type=EntityType.datastore,
            related_is_a=Relationship.PARENT,
            graph=graph_entity_service.to_graph(None, entity_models),
            entity_map=graph_entity_service.to_entity_map(entity_models),
            icon='◆',
        )
    ]

    for action_type in engine.data.supported_action_types:
        entity_models = graph_entity_service.to_entity_models_with_randomized_ids([
            Action(id=Ref.action(1), data=ActionData(
                name=action_type.name,
                action_type_name=action_type.name,
                engine_name=engine_name,
                datastore_id=Ref.parent(),
                state=ActionState.HAS_NEVER_RUN,
                args={} if action_type.params_json_schema else None
            ))
        ])
        sub_graph_map[EntityType.datastore].append(
            SubGraph(
                name=action_type.name,
                description=action_type.description,
                related_type=EntityType.datastore,
                related_is_a=Relationship.PARENT,
                graph=graph_entity_service.to_graph(None, entity_models),
                entity_map=graph_entity_service.to_entity_map(entity_models),
                icon='●',
            )

        )

    return sub_graph_map
