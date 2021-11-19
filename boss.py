# todo:
# After tech demo:
# todo:
#  Troll boss with custom AI
#  Troll Boss AI with ramming charge and summonning goblins

from monster import *


class Boss(Humanoid):
    difficulty = 0
    skirmish_spawn_rate = 0
    theme = 'blkrbt_ninesix.ogg'
    pct_cap = .02
    _dps_pct_cap = 0.005
    drops_shields = False
    remains_persistence = 0

    # Don't get disabled:
    def set_state(self, state, duration):
        super(Boss, self).set_state('active' if state in DISABLED else state, duration)

    # Remove bars; Scene should spawn giant HP bar:
    def __init__(self, *args, **kwargs):
        super(Boss, self).__init__(*args, **kwargs)
        self.bars.clear()

    # Instantly restore all stamina:
    def breath(self):
        super(Boss, self).breath()
        self.stamina = self.max_stamina

    # Never interrupted:
    def _interrupt_channel(self):
        return


class Elite(Boss):
    class_name = 'Elite'
    _size_modifier = 1.2
    _breakpoints = 3  # Reducing health below breakpoint causes the Boss to spawn reinforcements

    def __init__(self, position, tier: int, base_creature: type, pack_difficulty: int = 5, team_color=None):
        # Create a bigger version of base creature:
        body_stats = character_stats["body"][base_creature.__name__].copy()
        portraits = character_stats["mind"][base_creature.__name__].copy()

        # Disable regen, increase health:
        body_stats["size"] *= self._size_modifier
        body_stats["hp_restoration"] = 0
        body_stats["health"] = 1000 + 200*tier

        # These are class specific, so reset them to make them distinct for each boss:
        self.__class__.color = None
        self.__class__.blood = None

        # Initialize self:
        super().__init__(
            position,
            **body_stats,
            **colors['enemy'],
            faces=portraits,
            name=f"Elite {base_creature.__name__.capitalize()} Lv.{tier:.0f}"
        )

        # Create a base creature to 'steal' it's equipment and properties
        donor: Character = base_creature(position=None, tier=tier, team_color=team_color)

        # Get slots and coordinates
        self.slots = donor.slots
        self.body_coordinates = donor.body_coordinates.copy()
        scale_body(self.body_coordinates, self._size_modifier)

        for slot in filter(lambda x: x != 'hat', donor.slots):
            equipment = donor.slots[slot]
            if equipment:
                # Update equipment portrait and stats to match own size
                equipment.font_size = int(equipment.font_size * 1.2)
                equipment.generate()
                equipment.update_stats()
                equipment.redraw_loot()

                # Equip it
                self.equip(equipment, slot)

        # Equip crown
        crown = EliteCrown(BASE_SIZE * body_stats["size"], tier)
        self.equip(crown, 'hat')

        # Add AI:
        self.ai = EliteAI(
            self,
            summon=base_creature,
            pack_difficulty=pack_difficulty,
            tier=tier,
            team_color=team_color
        )

        # Breakpoint treshold:
        self.breakpoint_treshold = self._breakpoints / self.max_hp

    def hurt(self, *args, **kwargs) -> (bool, int):
        before_breakpoints = round(self.hp * self.breakpoint_treshold)
        output = super(Elite, self).hurt(*args, **kwargs)

        # Summon reinforcements if damage took self under a breakpoint:
        new_breakpoints = round(self.hp * self.breakpoint_treshold)
        if output[0] and before_breakpoints > new_breakpoints:
            self.ai.start_summon()

        return output


class EliteAI(AI):
    _reinforcement_cache_size = 15
    _summon_channel = 2
    _random_summon_chance = 0.5
    _random_summon_cooldown = 10000

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

        # Save options to create new ones on the go:
        self.minion = summon
        self.spawn_options = {
            'position': None,
            'tier': tier,
            'team_color': team_color
        }

        # Cooldown to spawn allies randomly:
        self.spawn_time = pygame.time.get_ticks()

        for _ in range(self._reinforcement_cache_size):
            minion = self.minion(**self.spawn_options)
            self.reinforcements.append(minion)

    def analyze(self, scene, initial=False):
        self._assess(scene)

        # If there are no friends, 50% to summon a new batch:
        if (
                not initial and
                self.character.hp < self.character.max_hp * 0.9 and
                not self.friends and
                random.random() > self._random_summon_chance and
                pygame.time.get_ticks() - self.spawn_time > self._random_summon_cooldown
        ):
            self.start_summon()
            return

        self._decide(initial)

    def _summon(self):
        self.spawn_time = pygame.time.get_ticks()
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

    def start_summon(self, phrase=None):

        phrase = phrase or random.choice(string['shout']['elite_summon'][self.minion.class_name])

        self.character.anchor(2, position=v(self.character.position))
        self.character.immune_timer = self.character.immune_timer_wall = 2

        self.spawn_time = pygame.time.get_ticks()
        self.push_away()
        self.character.channel(self._summon_channel, self._summon)
        self.scene.echo(self.character, phrase, self.character.attacks_color)

    def push_away(self):
        self.character.set_state('active', 1)
        self.scene.explosion(
            self.character.position,
            max_distance=self.character.hitbox[0].width * 2,
            max_push=1,
            collision_group=self.character.collision_group
        )

    # Bosses don't react to FOF events
    @staticmethod
    def fight_or_flight(victim, **kwargs):
        return
