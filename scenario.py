# todo:
#  return to menu after death or clearing Campaign
#  Player.fate: dict to remember player choices for future scenario
#  todo: scenario feeds dict with debug info into scene for display debug

from scene import *
from monster import *
from artifact import *


class Player(Humanoid):
    hit_immunity = 1.2

    def __init__(self, position):
        player_body = character_stats["body"]["human"].copy()
        player_body["agility"] *= 2

        super(Player, self).__init__(
            position,
            **player_body,
            **colors["player"],
            faces=character_stats["mind"]["human"],
            name="Fenci"
        )
        self.flip(new_collision=0)

    def push(self, vector, time, state='flying'):
        # Player character is more resilient to pushback
        if state in DISABLED:
            vector *= 0.33
        super().push(vector, time, state)

    def equip_basic(self, main_hand_pick=None, off_hand_pick=None):

        if main_hand_pick is None:
            main_hand_lst = list(
                filter(
                    lambda x:
                        artifacts[x]["class"] in {"Dagger", "Sword", "Spear", "Falchion"} and artifacts[x]["tier"] == 0,
                    artifacts
                )
            )
            main_hand_pick = random.choice(main_hand_lst), 'main_hand'
        else:
            main_hand_pick = main_hand_pick, 'main_hand'

        if off_hand_pick is None:
            off_hand_lst = list(
                filter(
                    lambda x: artifacts[x]["class"] in {"Shield", "Swordbreaker"} and artifacts[x]["tier"] == 0,
                    artifacts
                )
            )
            off_hand_pick = random.choice(off_hand_lst), 'off_hand'
        else:
            off_hand_pick = off_hand_pick, 'off_hand'

        for weapon in (main_hand_pick, off_hand_pick):
            weapon_gen = Wielded.registry[artifacts[weapon[0]]["class"]]
            generated = weapon_gen(24, equipment_dict=artifacts[weapon[0]])
            self.equip(generated, weapon[1])


class Campaign:
    """Create a campaign as sequence of dialogues and scenes being executed"""

    def __init__(self):
        pass


class SceneHandler:
    def __init__(
            self,
            tier: int,
            pad_monster_classes: list,
            monsters: list[Character] = None,
            loot_drops: int = 4,
            monster_total_cost: int = 100,
            on_scren_enemies_value=(6, 10),
            player: Player = None,
            scene: Scene = None,
            enemy_color=c(100, 0, 0),
            spawn_delay: float = (8.0, 2.0),
            sort_loot: bool = False
    ):
        # Dynamically changing:
        self.victory_banner = None
        self.loot_progression = 0
        self.absolute_progression = 0

        self.relative_progression = 0.0
        self.deserved_loot_drops = 0

        # Target tier to spawn monsters and loot:
        self.tier = tier

        # Spawn a player unless we have it ready from before:
        if player is None:
            self.player = Player(position=PLAYER_SPAWN)
            self.player.equip_basic()
        else:
            self.player = player

        # Initiate a new scene:
        self.scene = scene or Scene(self.player, SCREEN, SCENE_BOUNDS)

        # Create backlog of monsters:
        self.on_scren_enemies_value_range = on_scren_enemies_value
        self.monsters = monsters or []
        enemy_cost = sum(enemy.difficulty for enemy in self.monsters)
        # Fill level up to missing value by monsters of specified classes
        while enemy_cost < monster_total_cost:
            monster_class = random.choice(pad_monster_classes)
            enemy_cost += monster_class.difficulty
            # Insert in random spots EXCEPT for last: may contain Bosses
            insert_idx = random.randint(0, len(self.monsters) - 1) if self.monsters else 0
            self.monsters.insert(
                insert_idx,
                monster_class(position=None, tier=self.tier, team_color=enemy_color)
            )

        # Create backlog of loot
        # Spread by class:
        loot_by_slot = dict()
        for loot_class in tuple(Wielded.registry.values()):
            if loot_class.prefer_slot in loot_by_slot:
                loot_by_slot[loot_class.prefer_slot].append(loot_class)
            else:
                loot_by_slot[loot_class.prefer_slot] = [loot_class]

        loot_slots = list(loot_by_slot.keys())
        loot_slot_weights = [LOOT_OCCURRENCE_WEIGHTS[slot] for slot in loot_slots]

        self.loot = []
        for _ in range(3 * loot_drops):
            # Choose slot to generate piece of loot for:
            loot_classes = loot_by_slot[random.choices(population=loot_slots, weights=loot_slot_weights)[0]]
            loot_class = random.choice(loot_classes)
            self.loot.append(loot_class(tier_target=tier, size=BASE_SIZE))
        # Better loot last:
        if sort_loot:
            self.loot.sort(key=lambda x: x.tier, reverse=False)

        # Calculate "cost" of getting loot drop offered:
        self.loot_progression_required = monster_total_cost / loot_drops
        self.absolute_level_value = monster_total_cost

        # Spawn bars and loot drop indicator
        bar_size = BASE_SIZE
        items = {
            "LEVEL": Bar(bar_size, 10, colors["inventory_durability"], self.absolute_level_value,
                         base_color=colors['inventory_durability']),
            "LOOT": Bar(bar_size, 10, colors["inventory_durability"], self.loot_progression_required,
                        base_color=colors['inventory_durability']),
            "loot_drop": Indicator(ascii_draw(bar_size, "LOOT ON CLEAR!", c(colors["indicator_good"])))
        }
        item_order = ["LEVEL", "LOOT", "loot_drop"]
        self.scene.progression = ProgressionBars(items, item_order, font_size=bar_size)

        # Enemy spawn delays
        self.spawn_delay_range = spawn_delay
        self.spawn_queued: [None, Character] = None
        self.spawn_timer = 0

        # Own spawn delay
        self.respawn_banner: [None, Banner] = None
        self.game_over_banner: [None, Banner] = None
        self.player_survived = True

        # Support for looting sequence:
        self.loot_querried = False
        self.loot_total = loot_drops
        self.loot_dropped = 0

        # Spawn monsters for scene inception:
        on_screen_value = 0
        while on_screen_value < self.on_scren_enemies_value_range[0]:
            self.spawn_monster(force=True)
            on_screen_value = self.scene.count_enemies_value()

    def execute(self):
        # 1. Iterate the scene
        self.scene.iterate()

        # 2. Affect the scene:
        # 2.1. Check and spawn monsters if needed
        # Check if loot is queued to be spawned
        if not self.loot_querried and not self.scene.loot_overlay and not self.scene.paused:
            self.spawn_monster()

        # 2.2. Modify displayed scene bars according to progression
        # Calculate current progress:
        killed_value = sum(
            [
                monster.difficulty
                for monster in self.scene.dead_characters
                if self.player.collision_group != monster.collision_group
            ]
        )
        self.deserved_loot_drops = killed_value // self.loot_progression_required
        self.relative_progression = killed_value / self.absolute_level_value

        if (
                self.deserved_loot_drops > self.loot_dropped or
                (self.loot_total > self.loot_dropped and not self.monsters)
        ) and not self.loot_querried and self.spawn_timer <= 0:
            self.loot_dropped += 1
            self.loot_querried = True

        # Update progress bars
        if self.loot_querried or self.deserved_loot_drops > self.loot_dropped:
            loot_bar_value = self.loot_progression_required
        elif self.loot_dropped == self.loot_total:
            loot_bar_value = 0
        else:
            loot_bar_value = killed_value % self.loot_progression_required

        self.scene.progression.update([
            killed_value,
            loot_bar_value,
            self.loot_querried or self.deserved_loot_drops > self.loot_dropped
        ])
        # 2.3. Drop loot for player if scene is clear and progress is achieved
        if not self.scene.loot_overlay and self.loot_querried and self.scene.count_enemies_value() == 0 and not any([
            weapon
            for weapon in self.player.weapon_slots
            if self.player.slots[weapon] and self.player.slots[weapon].activation_offset != v()
        ]):
            loot_package = self.loot[:3]
            del self.loot[:3]
            loot_label = random.choice([
                'LOOT TIME!',
                'DESERVED!',
                'YOINK!',
                'YOURS NOW!',
                'FRESH FROM THE ENEMY POCKETS!',
                'UPGRADE TIME!',
                'GIMME, GIMME!',
                'WOW!',
                'FINDERS KEEPERS!',
                "IT IS DANGEROUS TO GO ALONE!",
                f'REWARD FOR {random.choice(["VALOUR", "COURAGE", "STRENGTH", "SKILL", "CUNNING"])}!',
                f'REWARD FOR {random.choice(["AGILITY", "RISKING", "STYLE", "PRECISION", "DODGING"])}!'
            ])
            # Animate overlay from last dead monster:
            last_victim = self.scene.dead_characters[-1].position
            self.scene.loot_overlay = LootOverlay(loot_package, self.player, label=loot_label, appear_from=last_victim)
            self.loot_querried = False

        # 2.4. Penalize and respawn dead player
        if self.player in self.scene.dead_characters:
            self.death_sequence()

        # 3. Test if scenario is done
        #  Test if scene is clear from enemies, no monsters left to spawn and all loot is picked up
        done = not any([
            self.monsters,
            self.scene.paused,
            self.loot_querried,
            self.scene.loot_overlay,
            any(char for char in self.scene.characters if char.collision_group != self.player.collision_group)
        ])

        # todo: Spawn victory banner
        if done:
            self.victory_banner = self.victory_banner or Banner(
                "placeholder",
                BASE_SIZE,
                self.scene.box.center,
                (255, 255, 255)
            )
            if self.victory_banner not in self.scene.particles:
                self.scene.particles.append(self.victory_banner)

        # Return True unless scenario is completed
        return not done

    def spawn_monster(self, force=False):
        # If forced, immediately spawn a monster. Exception unsafe!
        if force:
            self.scene.spawn(self.monsters.pop())
            return

        # Calculate current progression dependent variables:
        current_on_scren_enemies = round(lerp(self.on_scren_enemies_value_range, self.relative_progression))
        current_spawn_delay = lerp(self.spawn_delay_range, self.relative_progression)
        present_enemies_value = self.scene.count_enemies_value()

        # Execute querried spawn if timer reached 0:
        if self.spawn_queued and self.spawn_timer <= 0:
            self.scene.spawn(self.spawn_queued)
            self.spawn_queued = None

        # If there are no enemies and none are querried to spawn, reduce spawn_timer to 0.5:
        elif self.spawn_queued is None and present_enemies_value == 0 and any(self.monsters):
            self.spawn_queued = self.monsters.pop()
            self.spawn_timer = 0.5

        # Drop timer if spawn is querried but scene is empty:
        elif self.spawn_timer > 0.5 and present_enemies_value == 0 and any(self.monsters):
            self.spawn_timer = 0.5

        # If a spawn is queued, tick down timer
        elif self.spawn_timer > 0 and not self.scene.paused:
            # Tick down slower is scene is close to full
            tick_down_speed = 1 - present_enemies_value / current_on_scren_enemies
            iteration_tick = lerp((0, FPS_TICK), tick_down_speed)
            self.spawn_timer -= iteration_tick if tick_down_speed == 1 else 2*iteration_tick

        # If there are less enemies than needed and no spawn is queued, queue one
        elif self.spawn_queued is None and present_enemies_value < current_on_scren_enemies and any(self.monsters):
            self.spawn_queued = self.monsters.pop()
            self.spawn_timer = current_spawn_delay

    def death_sequence(self, respawn_bang=True):
        if self.game_over_banner:
            self.game_over_banner.lifetime = max(
                self.game_over_banner.lifetime,
                self.game_over_banner.max_lifetime - self.game_over_banner.animation_duration
            )

        elif self.respawn_banner is None:
            self.player_survived, report = self.player.penalize()
            # Spawn report banner
            report_position = WINDOW_SIZE[0] // 2, self.scene.box.bottom - BASE_SIZE
            report_banner = Banner(
                report,
                BASE_SIZE,
                report_position,
                colors["inventory_worse"],
                lifetime=7,
                animation_duration=3.5,
                animation='slide'
            )
            self.scene.particles.append(report_banner)

            if not self.player_survived:
                self.game_over_banner = Banner(
                    "GAME OVER",
                    BASE_SIZE * 2,
                    self.scene.box.center[:],
                    colors["game_over"],
                    lifetime=30,
                    animation_duration=3
                )
                self.scene.particles.append(self.game_over_banner)

                # Exit the loop
                return

            banner_text = random.choice([
                "PERSEVERANCE",
                "GET THEM, TIGER!",
                "FOCUS",
                "HARDER, BETTER, FASTER, STRONGER",
                "OUR WORK IS NEVER OVER",
                "GET BACK IN THERE",
                "THERE IS MORE TO LIFE",
                "CONFIDENCE",
                "COURAGE",
                "THAT WAS A MISTAKE",
                "MISTAKES WERE MADE",
                "AW, HECK",
                "DO A BARREL ROLL",
                "USE THE FORCE",
                "DODGE ENEMY ATTACKS",
                "COULD BE WORSE",
                "THAT WAS CLOSE",
                "HATERS GONNA HATE",
                "SHAKE IT OFF",
                "BLOOD FOR THE BLOOD GOD",
                "WHAT DOESN'T KILL YOU...",
                "YOU CAN DO THIS",
                "LOK'TAR OGAR",
                "NOT THAT BAD, REALLY",
                "WORK THEM FEET",
                "CAREFUL",
                "I'VE SEEN WORSE"
            ])
            self.respawn_banner = Banner(
                banner_text,
                BASE_SIZE * 2,
                self.scene.box.center[:],
                colors["respawn_encourage"],
                lifetime=3,
                animation_duration=0.3
            )

            self.scene.particles.append(self.respawn_banner)

        elif self.respawn_banner.lifetime <= 0:
            if respawn_bang:
                # Push enemies away:
                for enemy in filter(lambda x: x.collision_group != self.player.collision_group, self.scene.characters):
                    direction = v(enemy.position) - v(PLAYER_SPAWN)
                    direction.scale_to_length(SWING_THRESHOLD)
                    enemy.push(direction, 1.2)

                # Spawn sparks:
                for _ in range(random.randint(7, 12)):
                    spark_v = v()
                    spark_v.from_polar((1.5 * SWING_THRESHOLD, random.uniform(-180, 180)))
                    spark = Spark(
                        position=PLAYER_SPAWN[:],
                        weapon=None,
                        vector=spark_v,
                        attack_color=colors["lightning"]
                    )
                    self.scene.particles.append(spark)

            self.scene.respawn(self.player, PLAYER_SPAWN)
            self.respawn_banner = None
