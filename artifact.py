# After tech demo
# Todo: artifact weapons with custom properties
# "survivor's mace": {},
# "hunting bow": {}

import base_class as b


class Artifact(b.Equipment):
    def description(self):
        return_string = super(Artifact, self).description()
        return f"Artifact {return_string[0].lower()}{return_string[1:]}"
