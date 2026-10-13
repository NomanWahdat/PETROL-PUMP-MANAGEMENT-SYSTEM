from rest_framework import serializers


class ExactDecimal(serializers.DecimalField):
    """Keep binary floating-point values out of financial and meter inputs."""
    def to_internal_value(self, data):
        if isinstance(data, float):
            raise serializers.ValidationError("Send decimal values as strings.")
        return super().to_internal_value(data)
