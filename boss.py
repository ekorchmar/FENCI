# todo:
#  Boss HP bar is drawn over entire scene
#  Scenes switch to boss themes
#  EliteAI: can summon additional enemies
#  EliteAI: disable fleeing
# After tech demo:
# todo:
#  Troll boss with custom AI
#  Troll Boss AI with ramming charge and summonning goblins

from monster import *


class Boss(Character):
    difficulty = 0
    skirmish_spawn_rate = 0
    _theme = 'blkrbt_stairs.ogg'
    pct_cap = .02
    dps_pct_cap = 0.005
    drops_shields = False

    # Don't get disabled
    def set_state(self, state, duration):
        super(Boss, self).set_state('active' if state in DISABLED else state, duration)


class Elite(Boss):
    class_name = 'Elite'
    _size_modifier = 1.2

    def __init__(self, position, tier: int, base_creature: type, pack_difficulty: int = 5, team_color=None):
        # Create a bigger version of base creature:
        body_stats = character_stats["body"][base_creature.__name__].copy()
        portraits = character_stats["mind"][base_creature.__name__].copy()

        # Disable regen, increase health:
        body_stats["size"] *= self._size_modifier
        body_stats["hp_restoration"] = 0
        body_stats["health"] = 1000 + 200*tier

        # Initialize self:
        super().__init__(
            position,
            **body_stats,
            **colors['enemy'],
            faces=portraits,
            name=f"Elite {base_creature.__name__.capitalize()} Lv.{tier:.0f}"
        )

        # Create a base creature to 'steal' it's equipment
        donor: Character = base_creature(position=None, tier=tier, team_color=team_color)
        for slot in donor.slots:
            equipment = donor.slots[slot]
            if equipment:
                # Update equipment portrait and stats to match own size
                equipment.font_size = int(equipment.font_size * 1.2)
                equipment.generate()
                equipment.update_stats()
                equipment.redraw_loot()

                # Equip it
                self.equip(equipment, slot)

        # todo: equip crown

        # Add AI:
        self.ai = EliteAI(
            self,
            summon=base_creature,
            pack_difficulty=pack_difficulty,
            tier=tier,
            team_color=team_color
        )


class EliteAI(AI):
    _reinforcement_cache_size = 15
    _summon_channel = 2

    def __init__(self, character, summon, pack_difficulty, tier, team_color, weapon_slot='main_hand'):
        super(EliteAI, self).__init__(
            character=character,
            weapon_slot=weapon_slot,
            aggression=1,
            skill=1,
            flexibility=1,
            courage=1
        )

        # Create backlog of summonable reinforcements (loop through them!)
        self.pack_difficulty = pack_difficulty
        self.reinforcements = list()
        self.summon_index = 0

        # Save option to create new ones on the go:
        self.minion = summon
        self.spawn_options = {
            'position': None,
            'tier': tier,
            'team_color': team_color
        }

        for _ in range(self._reinforcement_cache_size):
            minion = self.minion(**self.spawn_options)
            self.reinforcements.append(minion)

    # todo: add summoning sequence to exec and analyze

    def _summon(self):
        self.push_away()
        # Form list of summonable monsters:
        minions = list()
        difficulty = 0
        while difficulty < self.pack_difficulty:
            # Use cached minions, if cache is exhausted, generate new ones.
            if self.summon_index < self._reinforcement_cache_size:
                minion = self.reinforcements[self.summon_index]
                self.summon_index += 1
            else:
                minion = self.minion(**self.spawn_options)

            minions.append(minion)
            difficulty += minion.difficulty

        self.scene.monster_summon(
            summoner=self.character,
            monsters=minions
        )

    def start_summon(self, phrase="To me!"):
        self.push_away()
        self.scene.echo(self.character, phrase, self.character.attacks_color)
        self.character.channel(self._summon_channel, self._summon)

    def push_away(self):
        self.scene.explosion(
            self.character.position,
            max_distance=self.character.hitbox[0].width * 2,
            max_push=1,
            collision_group=self.character.collision_group
        )
