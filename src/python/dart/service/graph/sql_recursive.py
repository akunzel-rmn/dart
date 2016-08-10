RECURSIVE_SQL = """
    WITH RECURSIVE entity_graph(type, id, name, state, sub_type, related_type, related_id, related_is_a) AS (

        VALUES (:entity_type, :entity_id, :name, :state, :sub_type, NULL, NULL, NULL)

      UNION

        SELECT t.*
          FROM entity_graph g
          JOIN LATERAL (

                    -- ===============================================
                    --  this is just to coerce column names/types
                    -- ===============================================
                    SELECT ''::text AS type, ''::text AS id, ''::text AS name, ''::text AS state, ''::text AS sub_type, ''::text AS related_type, ''::text AS related_id, ''::text AS related_is_a
                     WHERE 0 = 1

                    UNION ALL

                    -- ===============================================
                    --  handle dataset relationships
                    -- ===============================================
                    SELECT 'action', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'action_type_name', 'dataset', g.id, 'PARENT'
                      FROM action e
                     WHERE g.type = 'dataset'
                       AND e.data ->> 'state' = 'TEMPLATE'
                       AND e.data #>> '{args,dataset_id}' = g.id

                    UNION ALL

                    SELECT 'action', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'action_type_name', 'dataset', g.id, 'PARENT'
                      FROM action e
                      JOIN dataset d
                        ON d.id = g.id
                     WHERE g.type = 'dataset'
                       AND e.data ->> 'state' = 'TEMPLATE'
                       AND e.data #>> '{args,destination_s3_path}' LIKE ((d.data ->> 'location') || '%')

                    UNION ALL

                    SELECT 'subscription', e.id, e.data ->> 'name', e.data ->> 'state', NULL, 'dataset', g.id, 'PARENT'
                      FROM subscription e
                     WHERE g.type = 'dataset'
                       AND e.data ->> 'dataset_id' = g.id

                    UNION ALL

                    -- ===============================================
                    --  handle action relationships
                    -- ===============================================
                    SELECT 'dataset', e.id, e.data ->> 'name', NULL, NULL, 'action', g.id, 'CHILD'
                      FROM dataset e
                      JOIN action a
                        ON a.id = g.id
                       AND a.data ->> 'state' = 'TEMPLATE'
                       AND a.data #>> '{args,dataset_id}' = e.id
                     WHERE g.type = 'action'

                    UNION ALL

                    SELECT 'dataset', e.id, e.data ->> 'name', NULL, NULL, 'action', g.id, 'CHILD'
                      FROM dataset e
                      JOIN action a
                        ON a.id = g.id
                       AND a.data #>> '{args,destination_s3_path}' LIKE ((e.data ->> 'location') || '%')
                       AND a.data ->> 'state' = 'TEMPLATE'
                     WHERE g.type = 'action'

                    UNION ALL

                    SELECT 'subscription', e.id, e.data ->> 'name', e.data ->> 'state', NULL, 'action', g.id, 'CHILD'
                      FROM subscription e
                      JOIN action a
                        ON a.id = g.id
                       AND a.data ->> 'state' = 'TEMPLATE'
                       AND a.data #>> '{args,subscription_id}' = e.id
                     WHERE g.type = 'action'

                    UNION ALL

                    (SELECT 'workflow', e.id, e.data ->> 'name', e.data ->> 'state', NULL, 'action', g.id, 'CHILD'
                      FROM workflow e
                      JOIN action a
                        ON a.id = g.id
                       AND a.data ->> 'state' = 'TEMPLATE'
                       AND a.data ->> 'workflow_id' = e.id
                     WHERE g.type = 'action'
                  ORDER BY CAST(a.data ->> 'order_idx' AS FLOAT))

                    UNION ALL

                    -- ===============================================
                    --  handle workflow relationships
                    -- ===============================================
                    (SELECT 'action', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'action_type_name', 'workflow', g.id, 'PARENT'
                      FROM action e
                     WHERE g.type = 'workflow'
                       AND e.data ->> 'state' = 'TEMPLATE'
                       AND e.data ->> 'workflow_id' = g.id
                  ORDER BY CAST(e.data ->> 'order_idx' AS FLOAT))

                    UNION ALL

                    SELECT 'datastore', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'engine_name', 'workflow', g.id, 'CHILD'
                      FROM datastore e
                      JOIN workflow w
                        ON w.id = g.id
                       AND w.data ->> 'datastore_id' = e.id
                     WHERE g.type = 'workflow'

                    UNION ALL

                    SELECT 'trigger', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'trigger_type_name', 'workflow', g.id, 'CHILD'
                      FROM trigger e
                     WHERE g.type = 'workflow'
                       AND g.id IN (SELECT value FROM jsonb_array_elements_text(e.data -> 'workflow_ids'))

                    UNION ALL

                    SELECT 'trigger', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'trigger_type_name', 'workflow', g.id, 'PARENT'
                      FROM trigger e
                     WHERE g.type = 'workflow'
                       AND e.data #>> '{args,completed_workflow_id}' = g.id

                    UNION ALL

                    SELECT 'trigger', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'trigger_type_name', 'workflow', g.id, 'PARENT'
                      FROM trigger e
                     WHERE g.type = 'workflow'
                       AND e.data #>> '{args,failed_workflow_id}' = g.id

                    UNION ALL

                    -- ===============================================
                    --  handle trigger relationships
                    -- ===============================================
                    SELECT 'workflow', e.id, e.data ->> 'name', e.data ->> 'state', NULL, 'trigger', g.id, 'PARENT'
                      FROM workflow e
                      JOIN trigger t
                        ON t.id = g.id
                       AND e.id IN (SELECT value FROM jsonb_array_elements_text(t.data -> 'workflow_ids'))
                     WHERE g.type = 'trigger'

                    UNION ALL

                    SELECT 'workflow', e.id, e.data ->> 'name', e.data ->> 'state', NULL, 'trigger', g.id, 'CHILD'
                      FROM workflow e
                      JOIN trigger t
                        ON t.id = g.id
                       AND t.data #>> '{args,completed_workflow_id}' = e.id
                     WHERE g.type = 'trigger'

                    UNION ALL

                    SELECT 'workflow', e.id, e.data ->> 'name', e.data ->> 'state', NULL, 'trigger', g.id, 'CHILD'
                      FROM workflow e
                      JOIN trigger t
                        ON t.id = g.id
                       AND t.data #>> '{args,failed_workflow_id}' = e.id
                     WHERE g.type = 'trigger'

                    UNION ALL

                    SELECT 'subscription', e.id, e.data ->> 'name', e.data ->> 'state', NULL, 'trigger', g.id, 'CHILD'
                      FROM subscription e
                      JOIN trigger t
                        ON t.id = g.id
                       AND t.data #>> '{args,subscription_id}' = e.id
                     WHERE g.type = 'trigger'

                    UNION ALL

                    SELECT 'event', e.id, e.data ->> 'name', e.data ->> 'state', NULL, 'trigger', g.id, 'CHILD'
                      FROM event e
                      JOIN trigger t
                        ON t.id = g.id
                       AND t.data #>> '{args,event_id}' = e.id
                     WHERE g.type = 'trigger'

                    UNION ALL

                    SELECT 'trigger', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'trigger_type_name', 'trigger', g.id, 'CHILD'
                      FROM trigger e
                      JOIN trigger t
                        ON t.id = g.id
                     WHERE g.type = 'trigger'
                       AND e.id IN (SELECT value FROM jsonb_array_elements_text(t.data #> '{args,completed_trigger_ids}'))

                    UNION ALL

                    SELECT 'trigger', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'trigger_type_name', 'trigger', g.id, 'PARENT'
                      FROM trigger e
                      JOIN trigger t
                        ON t.id = g.id
                     WHERE g.type = 'trigger'
                       AND t.id IN (SELECT value FROM jsonb_array_elements_text(e.data #> '{args,completed_trigger_ids}'))

                    UNION ALL

                    -- ===============================================
                    --  handle subscription relationships
                    -- ===============================================
                    SELECT 'dataset', e.id, e.data ->> 'name', e.data ->> 'state', NULL, 'subscription', g.id, 'CHILD'
                      FROM dataset e
                      JOIN subscription s
                        ON s.id = g.id
                       AND s.data ->> 'dataset_id' = e.id
                     WHERE g.type = 'subscription'

                    UNION ALL

                    SELECT 'action', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'action_type_name', 'subscription', g.id, 'PARENT'
                      FROM action e
                     WHERE g.type = 'subscription'
                       AND e.data ->> 'state' = 'TEMPLATE'
                       AND e.data #>> '{args,subscription_id}' = g.id

                    UNION ALL

                    SELECT 'trigger', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'trigger_type_name', 'subscription', g.id, 'PARENT'
                      FROM trigger e
                     WHERE g.type = 'subscription'
                       AND e.data #>> '{args,subscription_id}' = g.id

                    UNION ALL

                    -- ===============================================
                    --  handle datastore relationships
                    -- ===============================================
                    SELECT 'workflow', e.id, e.data ->> 'name', e.data ->> 'state', NULL, 'datastore', g.id, 'PARENT'
                      FROM workflow e
                      JOIN datastore d
                        ON d.id = g.id
                       AND d.id = e.data ->> 'datastore_id'
                     WHERE g.type = 'datastore'

                    UNION ALL

                    -- ===============================================
                    --  handle event relationships
                    -- ===============================================
                    SELECT 'trigger', e.id, e.data ->> 'name', e.data ->> 'state', e.data ->> 'trigger_type_name', 'event', g.id, 'PARENT'
                      FROM trigger e
                     WHERE g.type = 'event'
                       AND e.data #>> '{args,event_id}' = g.id

               ) t
            ON t.related_type = g.type
           AND t.related_id = g.id
    )
    SELECT * FROM entity_graph
    LIMIT 1000;
    """
