# todo:
#  Troll boss with modified AI
#  Boss HP bar is drawn over scene
#  Boss is resistant to pushback, disabling effects and pct damage
#  Troll Boss AI with ramming charge and summonning goblins

from monster import *


class Boss(Character):
    pct_cap = .02
    dps_pct_cap = 0.005

    # Don't get disabled
    def set_state(self, state, duration):
        super(Boss, self).set_state('active' if state in DISABLED else state, duration)


class BossAI(AI):
    pass

