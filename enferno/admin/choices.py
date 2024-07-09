import enum

class BaseChoices(enum.Enum):
    @classmethod
    def is_valid(cls, value):
        return value in cls._value2member_map_

    @classmethod
    def get_name(cls, value):
        return cls(value).name

    def __str__(self):
        return self.value

class Sex(BaseChoices):
    Man = 'Man'
    Woman = 'Woman'
    Unknown = 'Unknown'
    Non_Binary = 'Non-Binary'
    Transgender_Man = 'Transgender Man'
    Transgender_Woman = 'Transgender Woman'

class Reliability(BaseChoices):
    A = 'A'
    B = 'B'
    C = 'C'
    D = 'D'
    E = 'E'
    F = 'F'
