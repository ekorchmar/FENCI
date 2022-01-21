import base_class as b
import particle as pt
import equipment as eq
import monster as mo
import boss as bs
import menu as mn
import scene as sc
import concurrent.futures
from primitive import *


# Scene Handlers: 'brains' of Scenes
class SceneHandler:
    completed = False
    _batch_spawn_chance = 0.3
    theme = None
    # Stores persistent reference to active scene handler to help instances of SceneHandler exchange game states:
    active = None

    def __init__(
            self,
            tier: int,
            pad_monster_classes: list,
            pad_monster_weights: list = None,
            monsters: list = None,
            loot_drops: int = 4,
            monster_total_cost: int = 100,
            on_scren_enemies_value=(7, 12),
            player: mo.Player = None,
            scene=None,
            enemy_color=c(100, 0, 0),
            spawn_delay: float = (8.0, 2.0),
            sort_loot: bool = False,
            no_player: bool = False,
            next_level_options: dict = None,
            scene_background: s = None
    ):
        # If there is no active SceneHandler, proclaim self to be one:
        if SceneHandler.active is None:
            SceneHandler.active = self

        # Dynamically changing:
        self.victory_banner = None
        self.loot_progression = 0
        self.absolute_progression = 0

        self.relative_progression = 0.0
        self.deserved_loot_drops = 0

        # Target tier to spawn monsters and loot:
        self.tier = tier

        # Spawn a player unless we have it ready from before:
        if player is None and not no_player:
            self.player = mo.Player(position=PLAYER_SPAWN)
            self.player.equip_basic()
        else:
            self.player = player

        # Initiate a new scene, again, if needed:
        self.scene = scene or sc.Scene(self.player, SCREEN, SCENE_BOUNDS, custom_surface=scene_background)

        # If scene does not have a player, but we do, add it to scene:
        if self.scene.player is None and self.player is not None:
            self.introduce_player()

        # Create backlog of monsters:
        self.on_scren_enemies_value_range = on_scren_enemies_value
        self.monsters = monsters or []

        # If spawn weights are not specified, all are equal
        pad_monster_weights = pad_monster_weights or [1] * len(pad_monster_classes)
        enemy_cost = sum(enemy.difficulty for enemy in self.monsters)

        # Fill level up to missing value by monsters of specified classes
        # Define generation function:
        def gen_monster(idx, cls):
            self.monsters.insert(
                idx,
                cls(position=None, tier=self.tier, team_color=enemy_color)
            )

        # Get list of classes and indices
        index_class = []
        while enemy_cost < monster_total_cost:
            monster_class = random.choices(pad_monster_classes, pad_monster_weights)[0]
            enemy_cost += monster_class.difficulty
            # Insert in random spots EXCEPT for first: may contain bs.Bosses
            insert_idx = random.randint(1, len(self.monsters)) if self.monsters else 0
            index_class.append((insert_idx, monster_class))

        # Generate monsters:
        with concurrent.futures.ProcessPoolExecutor() as executor:
            executor.map(gen_monster, index_class)

        # Create backlog of loot
        # Spread by slot:
        self.loot = []
        self.generate_drops(queue=self.loot, amount=3*loot_drops)

        # Better loot last:
        if sort_loot:
            self.loot.sort(key=lambda x: x.tier, reverse=False)

        # Calculate "cost" of getting loot drop offered:
        self.loot_progression_required = monster_total_cost / loot_drops if loot_drops != 0 else 0
        self.absolute_level_value = monster_total_cost

        # Spawn bars and loot drop indicator
        self.fill_scene_progression()

        # Enemy spawn delays
        self.spawn_enemies = True
        self.spawn_delay_range = spawn_delay
        self.spawn_queued: [None, b.Character] = None
        self.spawn_timer = 0

        # Own spawn delay
        self.respawn_banner: [None, pt.Banner] = None
        self.player_survived = True

        # Support for looting sequence:
        self.loot_querried = False
        self.loot_total = loot_drops
        self.loot_dropped = 0
        self.batch_spawn_after_loot = False

        # Button that takes us to the next level (subclasses set own, this is just a skeleton):
        self.next_level_options = next_level_options or {
            "next_level_text": None,
            "next_level_action": None,
            "next_level_parameters": None,
            "next_level_keywords": None
        }

        # Play music
        if OPTIONS["music"] and self.theme and not pygame.mixer.music.get_busy():
            self.play_theme()

    def generate_drops(self, queue, amount):
        # Spread by slot:
        loot_by_slot = dict()
        for loot_class in tuple(eq.Wielded.registry.values()):
            if loot_class.prefer_slot in loot_by_slot:
                loot_by_slot[loot_class.prefer_slot].append(loot_class)
            else:
                loot_by_slot[loot_class.prefer_slot] = [loot_class]

        loot_slots = list(loot_by_slot.keys())
        loot_slot_weights = [LOOT_OCCURRENCE_WEIGHTS[slot] for slot in loot_slots]
        last_loot_classes = [None, None]

        for _ in range(amount):
            # Choose slot to generate piece of loot for:
            loot_classes = loot_by_slot[random.choices(population=loot_slots, weights=loot_slot_weights)[0]]
            # Prevent generating 3 of same class in a row:
            if last_loot_classes[0] is last_loot_classes[1] in loot_classes:
                loot_classes.remove(last_loot_classes[0])
            loot_class = random.choice(loot_classes)

            # Cycle last 2 classes:
            del last_loot_classes[0]
            last_loot_classes.append(loot_class)

            # Append loot piece
            queue.append(loot_class(tier_target=self.tier, size=BASE_SIZE))

    def introduce_player(self):
        self.scene.player = self.player
        if self.player not in self.scene.characters:
            self.scene.characters = [self.player] + self.scene.characters
        self.fill_scene_progression()
        self.scene.log_weapons()

    def fill_scene_progression(self):
        bar_size = BASE_SIZE
        items = {
            f"{string['progress']['level']}{self.tier}": b.Bar(
                bar_size,
                10,
                colors["inventory_durability"],
                self.absolute_level_value,
                base_color=colors['inventory_durability']
            ),
            string['progress']['loot_drop']: b.Bar(
                bar_size,
                10,
                colors["inventory_durability"],
                self.loot_progression_required,
                base_color=colors['inventory_durability']
            ),
            "loot_drop": sc.Indicator(ascii_draw(
                bar_size,
                string['progress']['loot_soon'],
                c(colors["indicator_good"])
            ))
        }
        self.scene.progression = sc.ProgressionBars(items, font_size=bar_size)

    def batch_spawn(self, value=None):
        self.batch_spawn_after_loot = False
        if value is None:
            value = lerp(self.on_scren_enemies_value_range, self.relative_progression)

        # Stop if monster backlog is empty
        while self.monsters and not isinstance(self.monsters[-1], bs.Boss) and self.scene.count_enemies_value() < value:
            self.spawn_monster(force=True)

    def execute(self) -> bool:
        # 1. Iterate the scene
        if not self.completed:
            self.scene.iterate()

        # 2. Affect the scene:
        # 2.1. Check and spawn monsters if needed
        # Test if loot is queued to be spawned
        if self.spawn_enemies and not any((self.loot_querried, self.scene.loot_overlay, self.scene.paused)):
            # If player just picked up loot, spawn a bunch of monsters:
            if self.batch_spawn_after_loot:
                self.batch_spawn()
            # If scene is empty and player is chainkilling spawning enemies, spawn bunch at once:
            elif (self.scene.count_enemies_value() == 0 and self.scene.enemies_count_on_death == []) or (
                    len(self.scene.enemies_count_on_death) > 3 and
                    self.scene.enemies_count_on_death[-3:] == [0, 0, 0] and
                    self.scene.count_enemies_value() == 0
            ):
                self.batch_spawn()
            # Otherwise, spawn normally
            else:
                self.spawn_monster()

        # 2.2. Modify displayed scene bars according to progress
        # Calculate current progress if player is present and loot is bound to drop:
        if self.player is not None and self.loot_total != 0:
            killed_value = sum(
                [
                    monster.difficulty
                    for monster in self.scene.dead_characters
                    if self.player.collision_group != monster.collision_group
                ]
            )
            self.deserved_loot_drops = killed_value // self.loot_progression_required \
                if self.loot_progression_required > 0 else 0
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

            if self.scene.progression:
                self.scene.progression.update([
                    killed_value,
                    loot_bar_value,
                    self.loot_querried or self.deserved_loot_drops > self.loot_dropped
                ])

        # 2.3. Drop loot for player if scene is clear and progress is achieved
        if (
                not self.scene.paused and
                not self.scene.loot_overlay and
                self.loot_querried and
                self.scene.count_enemies_value() == 0 and not
                any(corpse for corpse in self.scene.particles if isinstance(corpse, pt.Remains) and corpse.lifetime > 3)
        ):
            self.batch_spawn_after_loot = True
            self.drop_loot(self.loot[:3])
            del self.loot[:3]

            # Boolean toggles:
            self.loot_querried = False
            self.player.seen_loot_drops = True

        # 2.4. Penalize and respawn dead player
        if self.player in self.scene.dead_characters:
            self.death_sequence()

        # 3. Test if scenario is done
        #  Test if scene is clear from enemies, no monsters left to spawn and all loot is picked up
        done = not any([
            not self.player,
            self.monsters,
            self.scene.paused,
            self.loot_querried,
            self.spawn_queued,
            self.scene.loot_overlay,
            any(char for char in self.scene.characters if char.collision_group != self.player.collision_group),
            # Any non-persistent corpses
            any(
                corpse for corpse in self.scene.particles
                if isinstance(corpse, pt.Remains) and corpse.blitting_list[0][-1] is not None
            ),
            # Any unresolved drops from level boss
            any(
                boss for boss in self.scene.dead_characters if isinstance(boss, bs.Boss) and boss.loot
            )
        ])

        # Spawn victory menu
        if done and not any(victory for victory in self.scene.menus if isinstance(victory, mn.Victory)):
            self._win()

        # 4. If scene requests a new handler, hand over:
        self._process_handover()

        # Return True unless scenario is completed
        return not done

    def drop_loot(self, loot_package):
        # Loot label contains a hint if it's first in playthrough:
        loot_label = random.choice(
            string["gameplay"]["loot_label" if self.player.seen_loot_drops else "loot_label_first"]
        )

        # Animate overlay from last dead monster:
        last_victim = self.scene.dead_characters[-1].position + self.scene.conversion_v

        # Spawn explanation:
        if not self.player.seen_loot_drops:
            self.scene.menus.append(mn.LootHelp())
        self.scene.loot_overlay = sc.LootOverlay(
            loot_package,
            self.player,
            label=loot_label,
            appear_from=last_victim
        )

    def _process_handover(self):
        if self.scene.new_sh_hook is not None:
            self.hand_off_to(self.scene.new_sh_hook)

    def _win(self):
        self.scene.generate_menu_popup(
            menu_class=mn.Victory,
            keywords={
                "scene": self.scene,
                **self.next_level_options
            }
        )

    def spawn_monster(self, force=False):
        # If forced, immediately spawn a monster. Exception unsafe!
        if force:
            self.scene.spawn(self.monsters.pop())
            return

        # Calculate current progress dependent variables:
        current_on_scren_enemies = lerp(self.on_scren_enemies_value_range, self.relative_progression)
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
            self.spawn_timer -= iteration_tick if tick_down_speed == 1 else 2 * iteration_tick

        # If there are fewer enemies than needed and no spawn is queued, queue one
        elif self.spawn_queued is None and present_enemies_value < current_on_scren_enemies and self.monsters:

            # If next monsters is boss, wait until scene is clear from same team characters:
            next_monster = self.monsters[-1]
            if isinstance(next_monster, bs.Boss) and any(char for char in self.scene.characters
                                                         if next_monster.collision_group == char.collision_group):
                return

            self.spawn_timer = current_spawn_delay

            # Depending on progress, there is a chance to get batch spawn instead, increasing with progress
            if random.random() > self._batch_spawn_chance + (1 - self._batch_spawn_chance) * self.relative_progression:
                self.batch_spawn()
            else:
                self.spawn_queued = self.monsters.pop()

    def death_sequence(self, respawn_bang=True):

        if any(defeat for defeat in self.scene.menus if isinstance(defeat, mn.Defeat)):
            return

        elif self.respawn_banner is None:
            self.player_survived, report = self.player.penalize()
            # Spawn report banner
            self.scene.report(report, colors["inventory_worse"])

            if not self.player_survived:
                self.scene.generate_menu_popup(
                    menu_class=mn.Defeat,
                    keywords={"scene": self.scene}
                )
                # Exit the loop
                return

            banner_text = random.choice(string['gameplay']['respawn_successful'])
            play_sound('player_death', 1)
            self.respawn_banner = pt.Banner(
                banner_text,
                BASE_SIZE * 2,
                self.scene.box.center[:],
                colors["respawn_encourage"],
                lifetime=3,
                animation_duration=0.3
            )

            self.scene.particles.append(self.respawn_banner)

        elif self.respawn_banner.lifetime <= 0 and self.player not in self.scene.characters:
            self.scene.respawn(self.player, PLAYER_SPAWN)
            if respawn_bang:
                self.scene.explosion(
                    self.player.position,
                    max_distance=13 * BASE_SIZE,
                    collision_group=self.player.collision_group
                )
            self.respawn_banner = None

    def hand_off_to(self, scene_handler, give_player=True):
        if self is not SceneHandler.active:
            raise ValueError(f"{self} is not the active scene handler.")

        # Fade all menus:
        [menu.fade() for menu in self.scene.menus]

        # Tick down all banners:
        for banner in self.scene.particles:
            if isinstance(banner, pt.Banner):
                banner.tick_down = True

        # Transplant player.
        if not isinstance(scene_handler, MainMenuSceneHandler) and self.player is not None and give_player:
            scene_handler.player = scene_handler.scene.player = self.player

            # Also supplement to the scene character list:
            try:
                player_index = scene_handler.scene.characters.index(self.player)
                scene_handler.scene.characters[player_index] = self.player
            except ValueError:
                # Player is not supposed to be alive in the scene? That's alright.
                try:
                    player_index = scene_handler.scene.dead_characters.index(self.player)
                    scene_handler.scene.dead_characters[player_index] = self.player
                except ValueError:
                    # Special Handlers (CampaignHandler) may introduce player later
                    pass

            # Remind new SH to initiate on the scene:
            scene_handler.introduce_player()
            scene_handler.fill_scene_progression()

        # Give up control:
        SceneHandler.active = scene_handler

        # Switch theme:
        if OPTIONS["music"]:
            end_theme()
            if SceneHandler.active.theme is not None:
                SceneHandler.active.play_theme()

    def play_theme(self):
        theme = self.theme
        # If there is a bs.Boss, pick its theme instead
        for monster in self.scene.characters:
            if isinstance(monster, bs.Boss) and monster.theme is not None:
                theme = monster.theme
        play_theme(os.path.join('music', theme))

    def load_save(self, cls):
        return

    @classmethod
    def load(cls):
        pass

    def save(self, next_level=False):
        return

    @staticmethod
    def complete():
        SceneHandler.active.completed = True


class SkirmishSceneHandler(SceneHandler):
    theme = 'blkrbt_stairs.ogg'

    def __init__(self, tier: int, *args, player=None, on_scren_enemies_value=(7, 12), **kwargs):

        pad_monster_classes = list(filter(
            lambda cls: not cls.debug and not issubclass(cls, bs.Boss),
            b.Character.registry.values()
        ))
        pad_monster_weights = [monster_class.skirmish_spawn_rate for monster_class in pad_monster_classes]

        # Custom loot offering screens for newly spawning player:
        self.offer_off_hand = self.offer_main_hand = player is None
        player = player or mo.Player(position=PLAYER_SPAWN)  # Base scene handler would equip player automatically

        # Introduce boss monster:
        boss = bs.Elite(
            position=None,
            tier=tier,
            base_creature=random.choice(pad_monster_classes),
            pack_difficulty=on_scren_enemies_value[1] * 2 // 3
        )

        # Draw background (Lorem Ipsum currently)
        # todo: replace with tiles
        lorem_ipsum = s(ARENA_RECT.size)
        lorem_ipsum.fill(colors["background"])
        blit_cascade_text(
            surface=lorem_ipsum,
            font_size=BASE_SIZE * 3 // 2,
            text=string["lorem_ipsum"],
            xy_topleft=v(),
            right_offset=0,
            color=colors["background_noise"]
        )

        super().__init__(
            tier=tier,
            *args,
            player=player,
            monsters=[boss],
            pad_monster_classes=pad_monster_classes,
            pad_monster_weights=pad_monster_weights,
            on_scren_enemies_value=on_scren_enemies_value,
            scene_background=lorem_ipsum,
            **kwargs
        )

        # Make boss drop something:
        if tier < 4:
            boss.loot = []
            self.generate_drops(boss.loot, 3)

        # Make sure Victory Screen has a button to go to the next difficulty level
        if tier < 4:
            self.next_level_options = {
                "next_level_text": f"{string['menu']['difficulty']}: {tier + 1}",
                "next_level_action": self.scene.request_new_handler,
                "next_level_parameters": [SkirmishSceneHandler],
                "next_level_keywords": {
                    "kwargs": {
                        "tier": tier + 1,
                        "player": self.player,  # Make sure the player is handed over!
                        **kwargs
                    }
                }
            }

        # If no custom loot drops are needed, pause monster spawning, and add an unpause countdown:
        self.spawn_enemies = False
        if not any((self.offer_main_hand, self.offer_off_hand)):
            self._spawn_countdown()

        # Save state of level to the disc:
        if any(self.player.slots[slot] for slot in self.player.slots):
            self.save()

        self.fill_scene_progression()

    def _spawn_countdown(self):
        self.scene.particles.append(pt.CountDown(
            self._start_spawning,
            {},
            colors["pause_popup"],
            position=self.scene.box.center[:],
            go_text="FIGHT!",
            ignore_pause=False
        ))

    def _start_spawning(self):
        self.spawn_enemies = True
        # Spawn monsters for scene inception:
        self.batch_spawn(self.on_scren_enemies_value_range[0])

    def execute(self) -> bool:
        # If no custom loot drops are needed, proceed as normal:
        if self.spawn_enemies:

            # If boss had died holding drops, and player has no enemies in scene spawn loot drop:
            if (
                    self.scene.dead_characters and
                    isinstance(self.scene.dead_characters[-1], bs.Boss) and
                    self.scene.dead_characters[-1].loot
            ):
                self.drop_loot(self.scene.dead_characters[-1].loot)
                self.scene.dead_characters[-1].loot = None

            return super(SkirmishSceneHandler, self).execute()

        elif not any((self.offer_main_hand, self.offer_off_hand, self.scene.loot_overlay)):
            # Spawn enemies if there is no countdown to do so:
            if not any(countdown for countdown in self.scene.particles if isinstance(countdown, pt.CountDown)):
                self._spawn_countdown()

        # Usual processing:
        self.scene.iterate()
        self._process_handover()

        # Offer basic selection of artefacts for weapon slots:
        if self.scene.loot_overlay is None and self.offer_main_hand:
            self._skirmish_init_equip('main_hand')
            self.offer_main_hand = False
        elif self.scene.loot_overlay is None and self.offer_off_hand:
            self._skirmish_init_equip('off_hand')
            self.offer_off_hand = False

        return self.completed

    def _skirmish_init_equip(self, slot):
        weapon_classes = set(filter(
            lambda cls: eq.Wielded.registry[cls].prefer_slot == slot,
            eq.Wielded.registry.keys()
        ))
        main_hand_picks = random.sample(
            list(filter(
                lambda x:
                artifacts[x]["class"] in weapon_classes and
                artifacts[x]["tier"] == 0,
                artifacts
            )),
            3
        )

        loot_package = []
        for artifact in main_hand_picks:
            generator = eq.Wielded.registry[artifacts[artifact]["class"]]
            loot_package.append(generator(BASE_SIZE, equipment_dict=artifacts[artifact], roll_stats=False))

        # Loot label contains a hint if it's first in playthrough:
        loot_label = random.choice(string["gameplay"]["loot_label_arena"])

        self.scene.loot_overlay = sc.LootOverlay(
            loot_package,
            self.player,
            label=loot_label,
            appear_from=None,
            sound=False,
            banner=False
        )

    def save(self, next_level=False):
        save_dict = {
            'type': 'skirmish',
            'level': self.tier + 1 if next_level else self.tier,
            'offer': [self.offer_off_hand, self.offer_main_hand],
            'player': self.player.save(),
            'seed': None  # May be useful one day
        }
        save_state(save_dict)

    @classmethod
    def load(cls):
        saved_state = load_json('saved.json', directory='progress')

        # Rereate saved player:
        saved_player = mo.Player.load(saved_state['player'], position=PLAYER_SPAWN)

        # Create SceneHandler:
        handler = cls(tier=saved_state['level'], player=saved_player)

        # Player may have been saved without equipped weapons, so check save to supplement them:
        handler.offer_off_hand, handler.offer_main_hand = saved_state['offer']

        return handler

    def _win(self):
        super(SkirmishSceneHandler, self)._win()
        mark_skirmish_progress(self.tier)


class MainMenuSceneHandler(SceneHandler):
    _spawn_delay = 2
    _gladiator_capacity = 8
    theme = 'blkrbt_brokenlight.ogg'

    def __init__(self, web_prompt=False):

        self.challenger_classes: list = [
            gladiator for
            gladiator in b.Character.registry.values()
            if not (gladiator.debug or issubclass(gladiator, bs.Boss))
        ]
        self.spawned_collision_group = 1
        self.spawn_timer = 0

        # Create a custom scene
        main_menu_scene = sc.Scene(None, SCREEN, EXTENDED_SCENE_BOUNDS, decorative=True)

        super().__init__(
            tier=0,
            pad_monster_classes=[],
            monster_total_cost=0,
            loot_drops=0,
            no_player=True,
            scene=main_menu_scene
        )

        # Spawn MainMenu in the scene
        self.scene.generate_menu_popup(
            menu_class=mn.MainMenu,
            keywords={
                "scene": self.scene,
                "web_prompt": web_prompt and not PROGRESS["disable_web_prompt"]
            }
        )

        # If we start MMSH, that means Tutorial was completed or deliberately closed
        if not PROGRESS["tutorial_completed"]:
            tutorial_completed(True)

    def execute(self) -> bool:
        # Spawn a monster if less than N are present
        if len(self.scene.characters) < self._gladiator_capacity and self.spawn_timer <= 0:
            challenger_tier = random.choice(range(1, 5))
            new_challenger = random.choice(self.challenger_classes)(position=None, tier=challenger_tier)
            new_challenger.collision_group = self.spawned_collision_group
            self.monsters.append(new_challenger)
            self.spawn_monster(force=True)
            # Python is designed to indefinetely extend integers, so there is no upper bound to catch exceptions for
            # Besides, increment is expected to be occuring once per dozen seconds, so it is not imaginable to reach
            # any kind of memory limit during time person stares at the menu.
            self.spawned_collision_group += 1
            self.spawn_timer = self._spawn_delay
        else:
            self.spawn_timer -= FPS_TICK

        # 1. Iterate the scene
        if not self.completed:
            self.scene.iterate()
            self._process_handover()

        return self.completed

    def load_save(self, cls):
        self.hand_off_to(cls.load())


class TutorialSceneHandler(SceneHandler):
    theme = 'blkrbt_desert3.ogg'

    def fill_scene_progression(self):
        bar_size = BASE_SIZE
        items = {
            "esc_reminder": sc.Indicator(ascii_draw(
                BASE_SIZE,
                string["tutorial"]["escape"],
                colors["inventory_title"]
            )),
            "skip_reminder": sc.Indicator(ascii_draw(
                BASE_SIZE,
                string["tutorial"]["skip"],
                colors["inventory_title"]
            ))
            }
        self.scene.progression = sc.ProgressionBars(items, font_size=bar_size)

    def __init__(self):
        self.proceed_condition = None

        super(TutorialSceneHandler, self).__init__(
            pad_monster_classes=[],
            monster_total_cost=0,
            loot_drops=0,
            tier=0
        )

        # "Kidnap" inventory UI:
        self.player.inventory, self.stored_inventory = None, self.player.inventory

        # Tutorial stages:
        self.stages = [
            # Move stage:
            {
                "player_equipment": {"main_hand": eq.Sword(BASE_SIZE, tier_target=1)},
                "text": string["tutorial"]["move"],
                "dummies": [],
                "positions": [],
                "proceed_condition": lambda: (
                        self.player.position.x < self.scene.box.width * 0.5 and
                        not self.player.facing_right
                ),
                "preparation": self._teleport_left()
            },

            # Swing stage:
            {
                "player_equipment": {"main_hand": eq.Axe(BASE_SIZE, tier_target=1)},
                "text": string["tutorial"]["swing"],
                "dummies": [mo.make_dummy(mo.Orc, tier=1, position=None)],
                "positions": [v(self.scene.box.width - PLAYER_SPAWN[0], PLAYER_SPAWN[1])],
                "proceed_condition": lambda: (
                        self.scene.dead_characters and
                        not any(remains for remains in self.scene.particles if isinstance(remains, pt.Remains))
                ),
                "preparation": self._disable_activation
            },

            # Poke stage:
            {
                "player_equipment": {"main_hand": eq.Spear(BASE_SIZE, tier_target=1)},
                "text": string["tutorial"]["poke"],
                "dummies": [mo.make_dummy(mo.Human, tier=1, position=None)],
                "positions": [v(self.scene.box.width - PLAYER_SPAWN[0], PLAYER_SPAWN[1])],
                "proceed_condition": lambda: (
                        self.scene.dead_characters and
                        not any(remains for remains in self.scene.particles if isinstance(remains, pt.Remains))
                ),
                "preparation": self._disable_activation
            },

            # Sword stage:
            {
                "player_equipment": {"main_hand": eq.Sword(BASE_SIZE, tier_target=1)},
                "text": string["tutorial"]["sword"],
                "dummies": [mo.make_dummy(mo.Goblin, tier=1, position=None) for _ in range(3)],
                "positions": [
                    v(
                        self.scene.box.width - PLAYER_SPAWN[0],
                        self.scene.box.height * 0.5 + self.scene.box.height * (i + 1) / 8
                    )
                    for i
                    in range(3)
                ],
                "proceed_condition": lambda: (
                        len(self.scene.dead_characters) == 3 and
                        not any(remains for remains in self.scene.particles if isinstance(remains, pt.Remains))
                ),
                "preparation": self._disable_activation
            },

            # Stab stage:
            {
                "player_equipment": {"main_hand": eq.Sword(BASE_SIZE, tier_target=1)},
                "text": string["tutorial"]["stab"],
                "dummies": [mo.make_dummy(mo.Human, tier=1, position=None)],
                "positions": [v(self.scene.box.width - PLAYER_SPAWN[0], PLAYER_SPAWN[1])],
                "proceed_condition": lambda: (
                        self.scene.dead_characters and
                        not any(remains for remains in self.scene.particles if isinstance(remains, pt.Remains))
                ),
                "preparation": self._active_only
            },

            # Block stage:
            {
                "player_equipment": {"off_hand": eq.Shield(BASE_SIZE, tier_target=1)},
                "text": string["tutorial"]["shield"],
                "dummies": [],
                "positions": [],
                "proceed_condition": lambda: (
                        self.player.shielded and
                        self.player.stamina == self.player.max_stamina
                ),
                "preparation": self._limit_stamina
            },

            # Bash stage:
            {
                "player_equipment": {"off_hand": eq.Shield(BASE_SIZE, tier_target=1)},
                "text": string["tutorial"]["bash"],
                "dummies": [mo.make_dummy(mo.Goblin, tier=1, position=None, hp=10)],
                "positions": [v(self.scene.box.width - PLAYER_SPAWN[0], PLAYER_SPAWN[1])],
                "proceed_condition": lambda: (
                        self.scene.dead_characters and
                        not any(remains for remains in self.scene.particles if isinstance(remains, pt.Remains))
                )
            },

            # Dagger stage:
            {
                "player_equipment": {"main_hand": eq.Dagger(BASE_SIZE, tier_target=1)},
                "text": string["tutorial"]["dagger"],
                "dummies": [mo.make_dummy(mo.Goblin, tier=1, position=None, hp=10000)],
                "positions": [v(self.scene.box.center)],
                "proceed_condition": lambda: (
                        self.player.rolled_through and
                        self.player.phasing is False and
                        self.player.slots["main_hand"].lock_timer <= 0
                ),
                "preparation": self._break_weapon
            },

            # Falchion stage:
            {
                "player_equipment": {"main_hand": eq.Falchion(BASE_SIZE, tier_target=1)},
                "text": string["tutorial"]["falchion"],
                "dummies": [],
                "positions": [],
                "proceed_condition": lambda: (
                        0 < self.player.roll_cooldown < 0.5 and
                        self.player.phasing is False and
                        self.player.slots["main_hand"].lock_timer <= 0
                ),
                "preparation": self._limit_stamina
            },

            # Spear 1 stage:
            {
                "player_equipment": {"main_hand": eq.Spear(BASE_SIZE, tier_target=1)},
                "text": string["tutorial"]["spear1"],
                "dummies": [mo.make_dummy(mo.Orc, tier=1, position=None, hp=10000)],
                "positions": [v(self.scene.box.width - PLAYER_SPAWN[0], PLAYER_SPAWN[1])],
                "proceed_condition": lambda: (
                    any(
                        x for x in self.scene.characters
                        if x.bleeding_intensity > 0 and x.bleeding_timer < 0.1
                    )
                )
            },

            # Katar stage:
            {
                "player_equipment": {
                    "main_hand": eq.Falchion(BASE_SIZE, tier_target=4),
                    "off_hand": eq.Katar(BASE_SIZE, tier_target=4)
                },
                "text": string["tutorial"]["katar"],
                "dummies": [mo.make_dummy(mo.Orc, tier=1, position=None, hp=500)],
                "positions": [v(self.scene.box.width - PLAYER_SPAWN[0], PLAYER_SPAWN[1])],
                "proceed_condition": lambda: (
                        self.scene.dead_characters and
                        not any(remains for remains in self.scene.particles if isinstance(remains, pt.Remains))
                ),
                "preparation": self._cheat_katar
            },

            # Inventory stage:
            {
                "player_equipment":
                    {
                        "main_hand": eq.Sword(BASE_SIZE, tier_target=1, roll_stats=False),
                        "backpack": eq.Sword(BASE_SIZE, tier_target=4, roll_stats=False)
                    },
                "text": string["tutorial"]["inventory"],
                "dummies": [],
                "positions": [],
                "proceed_condition": lambda: (
                        not self.scene.paused and
                        not all((self.player.slots["backpack"], self.player.slots["main_hand"])) and
                        not any(
                            remains for remains in self.scene.particles
                            if isinstance(remains, pt.Remains)
                        )),
                "preparation": self._restore_inventory
            },

            # Swordbreaker stage:
            {
                "player_equipment": {
                    "main_hand": eq.Sword(BASE_SIZE, tier_target=1),
                    "off_hand": eq.Swordbreaker(BASE_SIZE, tier_target=4)
                },
                "text": string["tutorial"]["breaker"],
                "dummies": [mo.make_dummy(mo.Skeleton, tier=2, position=None)],
                "positions": [v(self.scene.box.width - PLAYER_SPAWN[0], PLAYER_SPAWN[1])],
                "proceed_condition": lambda: (
                        self.scene.dead_characters and
                        not any(remains for remains in self.scene.particles if isinstance(remains, pt.Remains))
                ),
                "preparation": self._limit_stamina
            },

            # Weight stage:
            {
                "player_equipment":
                    {
                        "main_hand": eq.Axe(BASE_SIZE, tier_target=1, roll_stats=False),
                        "backpack": eq.Dagger(BASE_SIZE, tier_target=4, roll_stats=False)
                    },
                "text": string["tutorial"]["weight"],
                "dummies": [mo.make_dummy(mo.Goblin, tier=1, position=None) for _ in range(3)],
                "positions": [
                    v(
                        self.scene.box.width - PLAYER_SPAWN[0],
                        self.scene.box.height * 0.5 + self.scene.box.height * (i + 1) / 8
                    )
                    for i
                    in range(3)
                    ],
                "proceed_condition": lambda: (
                        len(self.scene.dead_characters) == 3 and
                        not any(remains for remains in self.scene.particles if isinstance(remains, pt.Remains))
                    )
            },

            # Spear 2 stage:
            {
                "player_equipment": {
                    "main_hand": eq.Spear(BASE_SIZE, tier_target=1),
                    "backpack": eq.Dagger(BASE_SIZE, tier_target=4)
                },
                "text": string["tutorial"]["spear2"],
                "dummies": [mo.make_dummy(mo.Goblin, tier=1, position=None) for _ in range(3)],
                "positions": [
                    v(
                        self.scene.box.width - PLAYER_SPAWN[0],
                        self.scene.box.height * 0.5 + self.scene.box.height * (i + 1) / 8
                    )
                    for i
                    in range(3)
                ],
                "proceed_condition": lambda: (
                        len(self.scene.dead_characters) == 3 and
                        not any(remains for remains in self.scene.particles if isinstance(remains, pt.Remains))
                )
            },

            # Knife and Combo stage:
            {
                "player_equipment": {"off_hand": eq.Knife(BASE_SIZE, tier_target=1)},
                "text": string["tutorial"]["knife"],
                "dummies": [mo.make_dummy(mo.Human, tier=1, position=None, hp=300)],
                "positions": [v(self.scene.box.width - PLAYER_SPAWN[0], PLAYER_SPAWN[1])],
                "proceed_condition": lambda: (
                        self.scene.dead_characters and
                        not any(remains for remains in self.scene.particles if isinstance(remains, pt.Remains))
                ),
                "preparation": self._knife_stage
            },

        ]

        # Disable scene elements:
        self.saved_sp_restoration = self.player.stamina_restoration

        self.scene.combo_counter = None
        self.fill_scene_progression()

        self._tutorial_banner = None
        self._tutorial_stage(**self.stages[0])

    def _disable_activation(self):
        for slot in self.player.slots:
            self.player.slots[slot].activate = (lambda *args, **kwargs: None)

    def _teleport_left(self):
        self.player.position = v(self.scene.box.width - self.player.position.x, self.player.position.y)

    def _active_only(self):
        for slot, weapon in self.player.slots.items():
            if not weapon:
                continue
            weapon.is_dangerous = (lambda: self.player.state == 'active')

    def _limit_stamina(self):
        self.player.stamina = 0
        self.player.stamina_restoration *= 0.3
        self.player.since_dangerous_frame = -60

    def _break_weapon(self):
        for slot in self.player.slots:
            self.player.slots[slot].damage_range = 1, 1

    def _cheat_katar(self):
        for weapon in self.player.slots.values():
            if isinstance(weapon, eq.Katar):
                weapon.character_specific["stamina_drain"] = 0

    def _restore_inventory(self):
        self.player.inventory = self.stored_inventory
        self.scene.log_weapons()

    def _knife_stage(self):
        self.scene.introduce_combo()
        knife = self.player.slots["off_hand"]
        knife.combo_cutoff = 5

    def _tutorial_stage(
            self,
            player_equipment: dict,
            text: str,
            dummies: list[b.Character],
            positions: list[v],
            proceed_condition,
            preparation=None
    ):
        # Make sure player stamina restoration is normal for the stage
        self.player.stamina_restoration = self.saved_sp_restoration

        self._tutorial_banner = pt.Banner(
            text,
            BASE_SIZE * 3 // 2,
            position=v(self.scene.box.midtop) + v(0, BASE_SIZE),
            anchor='midtop',
            color=colors["inventory_better"],
            lifetime=0.6,
            animation_duration=0.3,
            animation='simple',
            forced_tickdown=False,
            max_width=self.scene.box.width - BASE_SIZE * 2
        )
        self.scene.particles.append(self._tutorial_banner)

        for dummy, position in zip(dummies, positions):
            self.scene.spawn(dummy, position)

        for slot in self.player.slots:
            if slot not in player_equipment:
                player_equipment[slot] = b.Nothing()

        for slot, equipment in player_equipment.items():
            self.player.equip(equipment, slot)

        self.scene.log_weapons()

        self.proceed_condition = proceed_condition

        if preparation is not None:
            preparation()

    def next_stage(self):

        if self.stages:
            del self.stages[0]

        # Reset scene:
        self.proceed_condition = None
        self.scene.dead_characters = []
        self.scene.characters = [self.player]
        exhaust = [particle for particle in self.scene.particles if particle.shakeable]
        for particle in exhaust:
            self.scene.particles.remove(particle)

        # Stop tutorial if everything is over
        if not self.stages and not self.scene.menus:
            self._tutorial_banner.forced_tickdown = True
            self._win()
            return

        # Play sound:
        play_sound('loot', 1)

        # Reset player
        self.player.position = v(PLAYER_SPAWN)
        if not self.player.facing_right:
            self.player.flip()
        self.player.reset()

        # Execute next stage:
        self._tutorial_banner.forced_tickdown = True
        self._tutorial_stage(**self.stages[0])

    def execute(self) -> bool:
        # Usual processing:
        if not self.completed:
            self.scene.iterate()
        self._process_handover()

        # Make sure indicators are visible
        self.scene.progression.update([True, True])

        # Check if current condition is fulfilled
        if self.proceed_condition is not None and self.proceed_condition():
            # Clean completed stage
            if self.stages:
                self.next_stage()

        return self.completed

    def _win(self):
        tutorial_completed(True)
        self.scene.generate_menu_popup(
            menu_class=mn.Victory,
            keywords={
                "scene": self.scene,
                "victory_text": string["tutorial"]["completed"]
            }
        )
