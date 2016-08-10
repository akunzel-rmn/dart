# coding=utf-8
from collections import defaultdict
import json

from sqlalchemy import text

from dart.context.database import db
from dart.context.locator import injectable
from dart.model.action import Action
from dart.model.dataset import Dataset
from dart.model.datastore import Datastore
from dart.model.event import Event
from dart.model.graph import GraphEntity, Graph, Node, Edge, Relationship, GraphEntityIdentifier, SubGraph, EntityType, \
    SubGraphDefinition
from dart.model.orm import SubGraphDefinitionDao
from dart.model.subscription import Subscription
from dart.model.trigger import Trigger
from dart.model.workflow import Workflow
from dart.service.graph.sql_recursive import RECURSIVE_SQL
from dart.service.graph.sql_misc import ENTITY_IDENTIFIER_SQL, DATASTORE_ONE_OFFS_SQL, WORKFLOW_INSTANCE_SQL
from dart.service.graph.sub_graph import get_static_subgraphs_by_engine_name, \
    get_static_subgraphs_by_engine_name_all_engines_related_none
from dart.util.rand import random_id


@injectable
class GraphEntityService(object):
    def __init__(self, engine_service, datastore_service, action_service):
        self._engine_service = engine_service
        self._datastore_service = datastore_service
        self._action_service = action_service

    def get_sub_graphs(self, related_type, related_engine_name):
        engine = None
        if related_engine_name:
            engine = self._engine_service.get_engine_by_name(related_engine_name)

        # merging (dictionary of lists)'s is easier with defaultdict
        sub_graphs_by_engine_name = defaultdict(list)

        # static subgraphs for the specified engine (or no engine)
        static_sub_graphs_by_engine_name = get_static_subgraphs_by_engine_name(engine, related_type, self)
        sub_graphs_by_engine_name.update(static_sub_graphs_by_engine_name)

        # engine provided subgraphs from the database
        db_sub_graphs = self._get_db_subgraphs_by_engine_name(related_engine_name, related_type)
        for engine_name, sub_graphs in db_sub_graphs.iteritems():
            sub_graphs_by_engine_name[engine_name].extend(sub_graphs)

        # static sub_graphs that are related to None
        if related_type is None:
            engine_names = self._engine_service.all_engine_names()
            unrelated_sub_graphs = get_static_subgraphs_by_engine_name_all_engines_related_none(engine_names, self)
            for engine_name, sub_graphs in unrelated_sub_graphs.iteritems():
                sub_graphs_by_engine_name[engine_name].extend(sub_graphs)

        return sub_graphs_by_engine_name

    def _get_db_subgraphs_by_engine_name(self, related_engine_name, related_type):
        query = SubGraphDefinitionDao.query
        if related_engine_name:
            query = query.filter(SubGraphDefinitionDao.data['engine_name'].astext == related_engine_name)
        if related_type:
            query = query.filter(SubGraphDefinitionDao.data['related_type'].astext == related_type)
        else:
            query = query.filter(SubGraphDefinitionDao.data['related_type'] == 'null')

        sub_graph_map = {}
        for e in query.all():
            sg_def = e.to_model()
            assert isinstance(sg_def, SubGraphDefinition)
            entity_models = self.to_entity_models_with_randomized_ids(
                sg_def.data.actions +
                sg_def.data.datasets +
                sg_def.data.datastores +
                sg_def.data.events +
                sg_def.data.subscriptions +
                sg_def.data.triggers +
                sg_def.data.workflows
            )
            engine_name = sg_def.data.engine_name
            entity_type = sg_def.data.related_type
            sub_graph = SubGraph(
                name=sg_def.data.name,
                description=sg_def.data.description,
                related_type=entity_type,
                related_is_a=sg_def.data.related_is_a,
                graph=self.to_graph(engine_name, entity_models),
                entity_map=self.to_entity_map(entity_models),
                icon=sg_def.data.icon,
                md_icon=sg_def.data.md_icon,
            )
            if engine_name not in sub_graph_map:
                sub_graph_map[engine_name] = []
            sub_graph_map[engine_name].append(sub_graph)

        return sub_graph_map

    def to_graph(self, engine_name, entity_models):
        visited_nodes = set()
        visited_edges = set()
        nodes = []
        edges = []

        for entity in entity_models:
            if isinstance(entity, Dataset):
                self._add_node(nodes, visited_nodes, 'dataset', entity.id, entity.data.name, None, None)

            if isinstance(entity, Action):
                self._add_node(nodes, visited_nodes, 'action', entity.id, entity.data.name, entity.data.state, entity.data.action_type_name)
                if entity.data.args and 'dataset_id' in entity.data.args:
                    self._add_edge(edges, visited_edges, 'dataset', entity.data.args['dataset_id'], 'action', entity.id)
                if entity.data.args and 'subscription_id' in entity.data.args:
                    self._add_edge(edges, visited_edges, 'subscription', entity.data.args['subscription_id'], 'action', entity.id)
                if entity.data.workflow_id:
                    self._add_edge(edges, visited_edges, 'workflow', entity.data.workflow_id, 'action', entity.id)
                if entity.data.datastore_id:
                    self._add_edge(edges, visited_edges, 'datastore', entity.data.datastore_id, 'action', entity.id)

            if isinstance(entity, Workflow):
                self._add_node(nodes, visited_nodes, 'workflow', entity.id, entity.data.name, entity.data.state, None)
                if entity.data.datastore_id:
                    self._add_edge(edges, visited_edges, 'datastore', entity.data.datastore_id, 'workflow', entity.id)

            if isinstance(entity, Trigger):
                self._add_node(nodes, visited_nodes, 'trigger', entity.id, entity.data.name, entity.data.state, entity.data.trigger_type_name)
                if entity.data.workflow_ids:
                    for wf_id in entity.data.workflow_ids:
                        self._add_edge(edges, visited_edges, 'trigger', entity.id, 'workflow', wf_id)
                if entity.data.args and 'completed_trigger_ids' in entity.data.args:
                    for t_id in entity.data.args['completed_trigger_ids']:
                        self._add_edge(edges, visited_edges, 'trigger', t_id, 'trigger', entity.id)
                if entity.data.args and 'event_id' in entity.data.args:
                    self._add_edge(edges, visited_edges, 'event', entity.data.args['event_id'], 'trigger', entity.id)
                if entity.data.args and 'completed_workflow_id' in entity.data.args:
                    self._add_edge(edges, visited_edges, 'workflow', entity.data.args['completed_workflow_id'], 'trigger', entity.id)
                if entity.data.args and 'failed_workflow_id' in entity.data.args:
                    self._add_edge(edges, visited_edges, 'workflow', entity.data.args['failed_workflow_id'], 'trigger', entity.id)
                if entity.data.args and 'subscription_id' in entity.data.args:
                    self._add_edge(edges, visited_edges, 'subscription', entity.data.args['subscription_id'], 'trigger', entity.id)

            if isinstance(entity, Subscription):
                self._add_node(nodes, visited_nodes, 'subscription', entity.id, entity.data.name, entity.data.state, None)
                if entity.data.dataset_id:
                    self._add_edge(edges, visited_edges, 'dataset', entity.data.dataset_id, 'subscription', entity.id)

            if isinstance(entity, Event):
                self._add_node(nodes, visited_nodes, 'event', entity.id, entity.data.name, entity.data.state, None)

            if isinstance(entity, Datastore):
                self._add_node(nodes, visited_nodes, 'datastore', entity.id, entity.data.name, entity.data.state, engine_name)

        return Graph(nodes, edges)

    @staticmethod
    def get_entity_identifiers(search):
        statement = text(ENTITY_IDENTIFIER_SQL).bindparams(search=search)
        return [GraphEntityIdentifier(*r) for r in db.session.execute(statement)]

    def get_entity_graph(self, entity):
        """ :type entity: dart.model.graph.GraphEntity
            :rtype: dart.model.graph.Graph """

        statement = text(RECURSIVE_SQL).bindparams(
            entity_type=entity.entity_type,
            entity_id=entity.entity_id,
            name=entity.name,
            state=entity.state,
            sub_type=entity.sub_type
        )

        visited_nodes = set()
        visited_edges = set()
        nodes = []
        edges = []
        for e in [GraphEntity(*r) for r in db.session.execute(statement)]:
            self._add_node(nodes, visited_nodes, e.entity_type, e.entity_id, e.name, e.state, e.sub_type)

            if e.related_id:
                if e.related_is_a == Relationship.CHILD:
                    src_type = e.entity_type
                    src_id = e.entity_id
                    dst_type = e.related_type
                    dst_id = e.related_id
                else:
                    src_type = e.related_type
                    src_id = e.related_id
                    dst_type = e.entity_type
                    dst_id = e.entity_id

                self._add_edge(edges, visited_edges, src_type, src_id, dst_type, dst_id)

        # now that we have the base graph, add in the most recent workflow_instances and their actions,
        # as well as recent datastore actions that are not associated with any workflows (if any)
        wf_ids, wf_sql = self._get_workflow_instance_sql(nodes)
        d_ids, d_sql = self._get_datastore_one_offs(nodes)

        sql_parts = []
        if wf_sql:
            sql_parts.append('(' + wf_sql + ')')
        if d_sql:
            sql_parts.append('(' + d_sql + ')')

        if len(sql_parts) == 0:
            return Graph(nodes, edges)

        sql = '\nUNION ALL\n'.join(sql_parts)
        statement = text(sql.format(
            wf_ids=', '.join(["'" + wf_id + "'" for wf_id in wf_ids]),
            d_ids=', '.join(["'" + d_id + "'" for d_id in d_ids])
        ))

        for r in db.session.execute(statement):
            if r[0] == 'workflow':
                entity_type, wf_id, wfi_id, wfi_progress, wfi_state, a_id, a_name, a_state, a_sub_type = r
                name = 'workflow_instance - %s%%' % wfi_progress if wfi_state == 'RUNNING' else 'workflow_instance'
                self._add_node(nodes, visited_nodes, 'workflow_instance', wfi_id, name, wfi_state, None)
                self._add_edge(edges, visited_edges, 'workflow', wf_id, 'workflow_instance', wfi_id)
                if a_id:
                    self._add_node(nodes, visited_nodes, 'action', a_id, a_name, a_state, a_sub_type)
                    self._add_edge(edges, visited_edges, 'workflow_instance', wfi_id, 'action', a_id)
            else:
                entity_type, d_id, skip1, skip2, skip3, a_id, a_name, a_state, a_sub_type = r
                self._add_node(nodes, visited_nodes, 'action', a_id, a_name, a_state, a_sub_type)
                self._add_edge(edges, visited_edges, 'datastore', d_id, 'action', a_id)

        return Graph(nodes, edges)

    @staticmethod
    def _get_datastore_one_offs(nodes):
        d_sql = ''
        d_ids = [n.entity_id for n in nodes if n.entity_type == 'datastore']
        if len(d_ids) > 0:
            d_sql = DATASTORE_ONE_OFFS_SQL
        return d_ids, d_sql

    @staticmethod
    def _get_workflow_instance_sql(nodes):
        wf_sql = ''
        wf_ids = [n.entity_id for n in nodes if n.entity_type == 'workflow']
        if len(wf_ids) > 0:
            wf_sql = WORKFLOW_INSTANCE_SQL
        return wf_ids, wf_sql

    @staticmethod
    def _add_node(nodes, visited_nodes, e_type, e_id, name, state, sub_type):
        node_id = e_type + '-' + e_id
        if node_id not in visited_nodes:
            visited_nodes.add(node_id)
            nodes.append(Node(e_type, e_id, name, state, sub_type))

    @staticmethod
    def _add_edge(edges, visited_edges, s_type, s_id, d_type, d_id):
        edge_id = '%s-%s %s-%s' % (s_type, s_id, d_type, d_id)
        if edge_id not in visited_edges:
            visited_edges.add(edge_id)
            edges.append(Edge(s_type, s_id, d_type, d_id))

    @staticmethod
    def _get_entity_type(entity):
        if isinstance(entity, Dataset):
            return EntityType.dataset
        if isinstance(entity, Action):
            return EntityType.action
        if isinstance(entity, Workflow):
            return EntityType.workflow
        if isinstance(entity, Trigger):
            return EntityType.trigger
        if isinstance(entity, Subscription):
            return EntityType.subscription
        if isinstance(entity, Event):
            return EntityType.event
        if isinstance(entity, Datastore):
            return EntityType.datastore

    def to_entity_map(self, entity_models):
        return {self._get_entity_type(em) + '-' + em.id: em for em in entity_models}

    @staticmethod
    def to_entity_models_with_randomized_ids(entity_models):
        # To support editing multiple subgraphs concurrently, we need to randomize the ids.
        # This method takes advantage of JSON formatting (a bit hacky, but simple and fast).
        id_map = {}
        for e in entity_models:
            prefix = 'UNSAVED'
            if e.id.startswith('PARENT'):
                prefix = 'PARENT'
            if e.id.startswith('CHILD'):
                prefix = 'CHILD'
            id_map[e.id] = '%s-%s' % (prefix, random_id())

        results = []
        for em in entity_models:
            stringified_model = json.dumps(em.to_dict())
            for original_id, randomized_id in id_map.iteritems():
                stringified_model = stringified_model.replace('"%s"' % original_id, '"%s"' % randomized_id)
            cls = type(em)
            results.append(cls.from_dict(json.loads(stringified_model)))
        return results
