from django.db import models


class DecimalEquality(models.Func):
    """Exact NUMERIC equality on PostgreSQL; scale-aware checks on dev SQLite."""
    output_field = models.BooleanField()
    arity = 2

    def __init__(self, left, right, places, **kwargs):
        self.places = places
        super().__init__(left, right, **kwargs)

    def as_sql(self, compiler, connection, **extra_context):
        left, left_params = compiler.compile(self.source_expressions[0])
        right, right_params = compiler.compile(self.source_expressions[1])
        return f"(({left}) = ({right}))", [*left_params, *right_params]

    def as_sqlite(self, compiler, connection, **extra_context):
        left, left_params = compiler.compile(self.source_expressions[0])
        right, right_params = compiler.compile(self.source_expressions[1])
        tolerance = '0.' + '0' * self.places + '5'
        return f"(ABS(({left}) - ({right})) < {tolerance})", [*left_params, *right_params]
