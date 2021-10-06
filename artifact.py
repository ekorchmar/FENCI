# todo: more starting weapons
# After tech demo
# Todo: artifact weapons with custom properties
# "savage axe": {},
# "survivor's mace": {},
# "hunting bow": {}

from equipment import *


class Artifact(Equipment):
    def description(self):
        return_string = super(Artifact, self).description()
        return f"Artifact {return_string[0].lower()}{return_string[1:]}"
