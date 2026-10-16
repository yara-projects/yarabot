"""Deterministic tabular record mapping. Ambiguous columns never become fields."""

from pathlib import Path
import re

from school_imports import extract_source, ImportProblem


def header(value):
    return re.sub(r'[^a-z0-9]+', '', str(value).casefold())


def make_record_draft(kind, filename, content):
    from admin_app import RESOURCES
    resource = kind.partition('/')[2]
    if resource not in {'students', 'parents', 'teachers', 'departments', 'subjects', 'exams', 'timetable', 'class-teachers', 'class-sections'}:
        raise ImportProblem('This record type is not available for import.')
    spec = RESOURCES[resource]
    names = {header(field['key']): field['key'] for field in spec['fields']}
    names.update({header(field['label']): field['key'] for field in spec['fields']})
    # Explicit ID means update. No ID means create; never match people by name.
    names.update({'id': '_id', 'recordid': '_id'})
    if spec['pk'] != 'class':
        names[header(spec['pk'])] = '_id'
    aliases = {'studentname': 'name', 'parentname': 'name' if resource == 'parents' else 'parent_name', 'teachername': 'name',
               'feestatus': 'fees_status', 'attendancepercentage': 'attendance_pct', 'rollnumber': 'roll_no'}
    names.update({key: value for key, value in aliases.items() if value in {field['key'] for field in spec['fields']}})
    source = extract_source(filename, content)
    rows, warnings = [], list(source['warnings'])
    fields = [field['key'] for field in spec['fields']]
    for table in source['tables']:
        if not table:
            continue
        mapping = {index: names[header(value)] for index, value in enumerate(table[0]) if header(value) in names}
        if len(set(mapping.values())) != len(mapping):
            raise ImportProblem('Multiple columns map to the same field. Rename the ambiguous source headers and extract again.')
        ignored = [str(value) for value in table[0] if str(value).strip() and header(value) not in names]
        if ignored:
            warnings.append('Unmapped columns were NOT imported: ' + ', '.join(ignored)[:1000])
        if not mapping:
            continue
        for source_row in table[1:]:
            row = {**dict.fromkeys(fields, ''), '_id': '', '_revision': ''}
            for index, key in mapping.items():
                row[key] = str(source_row[index] if index < len(source_row) and source_row[index] is not None else '').strip()
            if spec['pk'] == 'class' and row['_id']:
                row['class'] = row['_id']
            rows.append(row)
    if len(rows) > 1000:
        raise ImportProblem('Split the source into at most 1,000 records.')
    warnings.append('Review every field. Missing columns are blank, not inferred. Existing IDs update exactly that record; blank IDs create new records. Publication applies the entire batch in one transaction, or none of it. Withdraw does not undo already applied record edits.')
    return dict(kind=kind, filename=Path(filename.replace('\\', '/')).name[:180], source_text=source['text'], rows=rows,
                warnings=warnings, suggested_scope={}, columns=['_id', *fields, '_revision'])
