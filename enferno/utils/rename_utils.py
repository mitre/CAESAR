def export_json_rename_handler(table_dict):

    def rename_relation_items(relations):
        for relation in relations:
            if 'bulletin' in relation:
                relation['primary_record'] = relation.pop('bulletin')
            if 'incident' in relation:
                relation['investigation'] = relation.pop('incident')
        return relations

    if table_dict['class'] == 'bulletin':
        table_dict['class'] = 'primary_record'
    elif table_dict['class'] == 'incident':
        table_dict['class'] = 'investigation'

    if 'bulletin_to_consent_uses' in table_dict:
        table_dict['consent_use_relations'] = table_dict.pop('bulletin_to_consent_uses')

    if 'bulletin_relations' in table_dict:
        table_dict['bulletin_relations'] = rename_relation_items(table_dict['bulletin_relations'])
        table_dict['primary_record_relations'] = table_dict.pop('bulletin_relations')
    if 'incident_relations' in table_dict:
        table_dict['incident_relations'] = rename_relation_items(table_dict['incident_relations'])
        table_dict['investigation_relations'] = table_dict.pop('incident_relations')
    if 'actor_relations' in table_dict:
        table_dict['actor_relations'] = rename_relation_items(table_dict['actor_relations'])
    if 'organization_relations' in table_dict:
        table_dict['organization_relations'] = rename_relation_items(table_dict['organization_relations'])
    return table_dict
