"""A simple sql expression builder.

This provides similar functionality to an ORM or sqlalchemy's expression sublanguage.
The main difference is that

i. We don't require an schema definition to work
ii. We do not handle conntions

This library merely builds sql expressions.

"""

class Query(object):
    "A complete sql query"
    def __init__(self, action='SELECT', table='timeseries', fields=None):
        self.action = action
        self.table = table
        self.insert_fields = []
        self.insert_values = []
        self.insert_expressions = []
        self.where_values = []
        self.conditions = []
        if fields is None:
            self.fields = ('*',) if action == 'SELECT' else None
        else:
            self.fields = fields

        if self.action == 'DELETE':
            if fields is not None:
                raise Exception('Cannot delete with fields')

        self.order_key = None
        self._offset = None
        self._limit = None

    def insert_field(self, field, value):
        self.insert_field_expression(field, '?', value)

    def insert_field_expression(self, field, expression, *values):
        if not self._is_inserting():
            raise Exception('Can only use insert_field if inserting ({})'.format(self.action))

        self.insert_fields.append(field)
        self.insert_expressions.append(expression)
        self.insert_values.extend(values)

    def _is_inserting(self):
        return self.action in ('INSERT', 'INSERT OR REPLACE')

    def where_equals(self, key, value):
        self.conditions.append('{} = ?'.format(key))
        self.where_values.append(value)

    def where_expression(self, expression):
        self.conditions.append(expression.query())
        self.where_values.extend(expression.values())

    def offset(self, offset):
        self._offset = offset

    def limit(self, limit):
        self._limit = limit

    def where(self, condition, *values):
        self.conditions.append(condition)
        self.where_values.extend(values)

    def order(self, key, reverse=False):
        if reverse:
            self.order_key = '{} DESC'.format(key)
        else:
            self.order_key = key

    def query(self):
        if self.fields:
            field_string = ','.join(self.fields)
        else:
            field_string = ''

        if self.conditions:
            condition_string = 'WHERE ' + ' AND '.join(self.conditions)
        else:
            condition_string = ''

        if self.order_key:
            order_string = 'ORDER BY {}'.format(self.order_key)
        else:
            order_string = ''

        if self._limit:
            limit_string = 'LIMIT {}'.format(self._limit)
        else:
            limit_string = ''

        if self._offset:
            offset_string = 'OFFSET {}'.format(self._offset)
        else:
            offset_string = ''

        if self.action in ('SELECT', 'DELETE'):
            return '''{action} {field_string} FROM {table} {condition_string} {order_string} {limit_string} {offset_string}'''.format(
                action=self.action,
                field_string=field_string,
                table=self.table,
                condition_string=condition_string,
                order_string=order_string,
                limit_string=limit_string,
                offset_string=offset_string,
                )
        elif self._is_inserting():
            insert_field_string = ', '.join(self.insert_fields)

            return '{action} INTO {table}({insert_field_string}) VALUES ({insert_expressions})'.format(
                action=self.action,
                table=self.table,
                insert_field_string=insert_field_string,
                insert_expressions=', '.join(self.insert_expressions),
                )
        else:
            raise ValueError(self.action)

    def values(self):
        return self.insert_values + self.where_values


class Expression(object):
    "An SQL value forming part of a where condition, or selected value"

class Or(Expression):
    def __init__(self):
        self._expressions = []
        self._values = []

    def add_equals(self, key, value):
        self._values.append(value)
        self._expressions.append('{} = ?'.format(key))

    def query(self):
        return '(' +  ' OR '.join(self._expressions) + ')'

    def values(self):
        return self._values
