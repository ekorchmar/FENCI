import particle as pt
import handler as hd
import webbrowser as wb
from primitive import *


# Menu primitives:
class Button:
    def __init__(
            self,
            text: list,
            rect: r,
            action,
            action_parameters: list = None,
            action_keywords: dict = None,
            size: int = BASE_SIZE,
            mouse_over_text: list = None,
            kb_index: int = None
    ):
        # Basis:
        self.text = text
        self.mouse_over_text = mouse_over_text or self.text
        self.action = action
        self.action_parameters = action_parameters or list()
        self.action_keywords = action_keywords or dict()

        # Activation handles:
        self.disabled = False
        self.rect = rect
        self.kb_index = kb_index

        # Create surfaces:
        # Text content:
        text_surface = ascii_draw_rows(size, [[row, colors["inventory_text"]] for row in self.text])
        text_rect = text_surface.get_rect(center=v(self.rect.center) - v(self.rect.topleft))
        text_surface_moused = ascii_draw_rows(size, [[row, colors["inventory_text"]] for row in self.mouse_over_text])
        text_moused_rect = text_surface_moused.get_rect(center=v(self.rect.center) - v(self.rect.topleft))
        disabled_surface = ascii_draw_rows(size, [[row, colors["inventory_description"]] for row in self.text])

        # Unmoused:
        self.surface = s(rect.size, pygame.SRCALPHA)
        self.surface.fill(c(colors["loot_card"]))
        frame_surface(self.surface, colors["inventory_text"])
        self.surface.blit(text_surface, text_rect)

        # If index is specified, add it to unmoused surface:
        if kb_index is not None:
            index_surface = ascii_draw(size * 2 // 3, NUMBER_LABELS[kb_index], colors["inventory_title"])
            self.surface.blit(index_surface, (BASE_SIZE // 2, BASE_SIZE // 2))

        # Moused:
        self.moused_over_surface = self.surface.copy()
        self.moused_over_surface.fill(c(colors["inventory_description"]))
        frame_surface(self.moused_over_surface, colors["inventory_text"])
        self.moused_over_surface.blit(text_surface_moused, text_moused_rect)

        # Disabled
        self.disabled_surface = self.surface.copy()
        self.disabled_surface.fill(c(colors["loot_card"]))
        frame_surface(self.disabled_surface, colors["inventory_text"])
        self.disabled_surface.blit(disabled_surface, text_rect)

    def draw(self, moused_over: bool):
        if self.disabled:
            return self.disabled_surface, self.rect
        return self.moused_over_surface if moused_over else self.surface, self.rect

    def activate(self):
        play_sound('button', 0.5)
        if self.disabled:
            return
        self.action(*self.action_parameters, **self.action_keywords)


class TNT:
    def __init__(self):
        self.banners = []
        self.box = hd.SceneHandler.active.scene.box
        self.update_banners()

    def update_banners(self):
        # Info strings options:
        info_string = {
            "size": BASE_SIZE * 2 // 3,
            "max_width": self.box.width - BASE_SIZE * 2,
            "lifetime": 0.6,
            "animation_duration": 0.3,
            "tick_down": False,
            "animation": 'simple',
            "anchor": 'bottomleft'
        }

        # Trivia string at the bottom, greyed out
        trivia_bottomleft = (self.box.left + BASE_SIZE, self.box.bottom - BASE_SIZE)
        trivia_banner = pt.Banner(
            text=f"{string['gameplay']['trivia_label']}: {random.choice(string['trivia'])}",
            position=trivia_bottomleft,
            color=colors["inventory_description"],
            **info_string
        )

        # Tip string above trivia string
        trivia_banner_top = trivia_banner.surface.get_rect(bottomleft=trivia_bottomleft).top
        tip_banner = pt.Banner(
            text=f"{string['gameplay']['tip_label']}: {random.choice(string['tips'])}",
            position=(self.box.left + BASE_SIZE, trivia_banner_top - BASE_SIZE // 2),
            color=colors["inventory_text"],
            **info_string
        )

        self.banners = [tip_banner, trivia_banner]

    def draw(self, pause):
        return [banner.draw(pause) for banner in self.banners]


# All kinds of menus and menu-like objects
class Menu:
    _background_color = c(*colors["loot_card"], 127)

    def __init__(
            self,
            buttons_list: list,
            rect: r = None,
            decoration_objects: list = None,
            background: bool = False,
            offset: int = BASE_SIZE,
            reposition_buttons: tuple = None,
            escape_button_index: int = None,
            title_surface: s = None,
            add_tnt: bool = False
    ):

        # Remember position and contents:
        self.title = title_surface
        self.rect = rect
        self.buttons_list = buttons_list
        self.dimensions = reposition_buttons
        self.offset = offset
        self.decoration_objects = decoration_objects or list()
        self.fading = False
        self.exhausted = False

        # Remember which button is meant to be escape (unless specified, use max index):
        self.escape_button_index = escape_button_index if escape_button_index is not None else \
            max(button.kb_index for button in self.buttons_list)

        if reposition_buttons is not None:
            self.reorder_buttons(self.dimensions)

        if self.rect is None:
            # Form a new rect in middle of screen
            # Find bounds of rect by buttons and title surface
            left, right, top, bottom = None, None, None, None
            for button in buttons_list:
                if left is None or left > button.rect.left:
                    left = button.rect.left
                if top is None or top > button.rect.top:
                    top = button.rect.top
                if right is None or right < button.rect.right:
                    right = button.rect.right
                if bottom is None or bottom < button.rect.bottom:
                    bottom = button.rect.bottom

            # Recalculate for title:
            if self.title is not None:
                top -= self.title.get_height() + self.offset
                if self.title.get_width() > right - left:
                    left = (WINDOW_SIZE[0] - self.title.get_width()) // 2
                    right = left + self.title.get_width()

            self.rect = r(
                left - self.offset,
                top - self.offset,
                right - left + self.offset * 2,
                bottom - top + self.offset * 2
            )

        # Draw background if needed:
        self.background = s(self.rect.size, pygame.SRCALPHA)
        if background:
            self.background.fill(self._background_color)
            frame_surface(self.background, colors["inventory_text"])
        else:
            self.background.fill([0, 0, 0, 0])

        # Add tip and trivia if needed:
        self.tnt = TNT() if add_tnt else None

        # Modify rect if it is not supplied
        if self.title:
            title_rect = self.title.get_rect(midtop=(self.rect.width // 2, self.offset))
            self.background.blit(self.title, title_rect)

    def reorder_buttons(self, dimensions):
        rows, columns = dimensions

        # Find initial corner and size to place buttons
        # Assume all buttons to have same height
        column_height = rows * self.offset + self.buttons_list[0].rect.height * rows
        title_height = self.title.get_height() + self.offset if self.title else 0
        column_height += title_height

        # Work with max button width
        button_max_width = max(button.rect.width for button in self.buttons_list)
        column_width = columns * self.offset + columns * button_max_width

        buttons_box = r(0, 0, column_width, column_height)
        buttons_box.center = v(self.rect.center) - v(self.offset // 2, self.offset // 2) if self.rect \
            else (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2)

        # Place buttons in new box:
        button_in_row = 1
        top = buttons_box.top + self.offset + title_height
        left = buttons_box.left + self.offset

        for button in self.buttons_list:
            if button.rect.topleft != (0, 0):
                continue

            # Prevent modifying default mutable rect
            button.rect = button.rect.copy()
            button.rect.topleft = left, top
            top += button.rect.height + self.offset
            button_in_row += 1

            if button_in_row > rows:
                left += button_max_width + self.offset
                top = buttons_box.top + self.offset + title_height
                button_in_row = 1

    def display(self, mouse_v, active=True):
        draw_order = list()

        # Draw background first
        if not self.fading:
            draw_order.append((self.background, self.rect))

        # Draw buttons:
        for button in self.buttons_list:
            draw_order.append(button.draw(active and bool(button.rect.collidepoint(mouse_v))))

        # Decorate:
        for banner in self.decoration_objects:
            draw_order.append(banner.draw(not self.fading))

            # Despawn dead banners:
            if banner.lifetime < 0:
                self.decoration_objects.remove(banner)

        # Add Tips and Trivia if available:
        if self.tnt:
            draw_order.extend(self.tnt.draw(not self.fading))

        # Check if menu is still to be drawn:
        self.check_exhaustion()

        return draw_order

    def check_exhaustion(self):
        self.exhausted = not any((
            not self.fading,
            self.buttons_list,
            self.decoration_objects,
            (self.tnt.banners[0].lifetime > 0) if self.tnt else False
        ))

    def collide_button(self, mouse_v):
        """Perform button action for given x, y"""
        for button in self.buttons_list:
            if button.rect.collidepoint(mouse_v):
                self.process(button)
                break

    def index_button(self, index):
        for button in self.buttons_list:
            if button.kb_index == index:
                self.process(button)
                break

    def process(self, button):
        button.activate()
        if self.tnt and not self.fading:
            self.tnt.update_banners()

    def fade(self):
        """Remove all buttons, cause all banners to fade"""
        self.buttons_list = []
        self.fading = True


class Options(Menu):
    def fade(self):
        # Write options dict to json file
        with open(os.path.join('options', 'options.json'), 'w') as options_json:
            json.dump(OPTIONS, options_json, sort_keys=False, indent=2)
        super(Options, self).fade()

    def toggle(self, key):
        # Toggle an option and cause redrawing all buttons
        if isinstance(OPTIONS[key], bool):
            OPTIONS[key] = not OPTIONS[key]
        else:
            # Get possible options count from localization file
            options_count = len(string['menu']['option_contents'][key + '_states'])
            OPTIONS[key] = (OPTIONS[key] + 1) % options_count
        self.redraw()

        # Special scripts:
        if key == 'fullscreen':
            # Windowed mode grabs mouse by default
            OPTIONS["grab_mouse"] = True
            update_screen()
        elif key == "music":
            if OPTIONS["music"] == 0:
                end_theme()
            elif OPTIONS["music"] == 1 and hd.SceneHandler.active.theme:
                hd.SceneHandler.active.play_theme()
                pygame.mixer.music.set_volume(MUSIC_VOLUME*OPTIONS["music"] / 4)
            else:
                pygame.mixer.music.set_volume(MUSIC_VOLUME * OPTIONS["music"] / 4)

        elif key == 'sound':
            load_sound_profile(OPTIONS["sound"])

    def generate_buttons(self):
        button_rect = DEFAULT_BUTTON_RECT.copy()
        button_rect.width *= 2
        buttons_list = []
        i = 0
        for key in OPTIONS:
            if isinstance(OPTIONS[key], bool):
                option_state_text = string['menu']['option_contents']["bool"]["True" if OPTIONS[key] else "False"]
            else:
                option_state_text = string['menu']['option_contents'][key + '_states'][str(OPTIONS[key])]

            button_text = f"{string['menu']['option_contents'][key]}: {option_state_text}"

            buttons_list.append(Button(
                text=[button_text],
                action=self.toggle,
                action_keywords={'key': key},
                rect=button_rect,
                kb_index=i
            ))
            i += 1

            # Disable certain options conditionally:
            if OPTIONS["fullscreen"] and key == 'grab_mouse':
                buttons_list[-1].disabled = True

        # Add close button
        buttons_list.append(Button(
            text=[string["menu"]["back"]],
            action=self.fade,
            rect=button_rect,
            kb_index=i
        ))

        return buttons_list

    def __init__(self):
        super(Options, self).__init__(
            self.generate_buttons(),
            reposition_buttons=(4, 2),
            background=True,
            title_surface=ascii_draw(BASE_SIZE * 2, string["menu"]["options"].upper(), colors["inventory_title"])
        )

    def redraw(self):
        self.buttons_list = self.generate_buttons()
        self.reorder_buttons(self.dimensions)


class RUSureMenu(Menu):
    def __init__(
            self,
            confirm_text,
            action,
            action_parameters=None,
            action_keywords=None,
            title=string["menu"]["confirm_exit"]
    ):
        title_surface = ascii_draw(BASE_SIZE, title, colors["inventory_title"])
        button_rect = DEFAULT_BUTTON_RECT.copy()
        button_rect.width *= 2

        button_list = [
            Button(
                text=[confirm_text],
                action=action,
                action_parameters=action_parameters,
                action_keywords=action_keywords,
                kb_index=0,
                rect=button_rect
            ),
            Button(
                text=[string["menu"]["back"]],
                action=self.fade,
                kb_index=1,
                rect=button_rect
            )
        ]

        super(RUSureMenu, self).__init__(
            button_list,
            reposition_buttons=(2, 1),
            background=True,
            title_surface=title_surface,
            escape_button_index=1
        )


class PauseEnsemble(Menu):
    def __init__(self, scene):
        prompt_in_menu = not isinstance(hd.SceneHandler.active, hd.TutorialSceneHandler)

        # Unpause button:
        unpause_rect = DEFAULT_BUTTON_RECT.copy()
        unpause_rect.topleft = scene.box.left + BASE_SIZE, scene.box.top + BASE_SIZE
        unpause_button = Button(
            text=[string['menu']['unpause']],
            rect=unpause_rect,
            action=scene.toggle_pause,
            kb_index=0
        )

        # Options button:
        options_rect = DEFAULT_BUTTON_RECT.copy()
        options_rect.topleft = unpause_rect.right + BASE_SIZE, scene.box.top + BASE_SIZE
        options_button = Button(
            text=[string['menu']['options']],
            rect=options_rect,
            action=scene.generate_menu_popup,
            action_keywords={"menu_class": Options},
            kb_index=1
        )

        # Main menu button:
        menu_rect = DEFAULT_BUTTON_RECT.copy()
        menu_rect.topleft = options_rect.right + BASE_SIZE, scene.box.top + BASE_SIZE
        menu_button = Button(
            text=[string['menu']['main']],
            rect=menu_rect,
            action=scene.generate_menu_popup,
            action_keywords={
                "menu_class": RUSureMenu,
                "keywords": {
                    "title": string["menu"]["confirm_menu"],
                    "confirm_text": string['menu']['confirmed_menu'],
                    "action": scene.request_new_handler,
                    "action_parameters": [hd.MainMenuSceneHandler],
                    "action_keywords": {"kwargs": {"web_prompt": prompt_in_menu}}
                }
            },
            kb_index=2
        )

        # Ragequit button
        exit_rect = DEFAULT_BUTTON_RECT.copy()
        exit_rect.topleft = menu_rect.right + BASE_SIZE, scene.box.top + BASE_SIZE
        exit_button = Button(
            text=[string['menu']['exit_ingame']],
            rect=exit_rect,
            action=scene.generate_menu_popup,
            action_keywords={
                "menu_class": RUSureMenu,
                "keywords": {
                    "title": string["menu"]["confirm_exit"],
                    "confirm_text": string['menu']['confirmed_exit_ingame'],
                    "action": exit_game
                }
            },
            kb_index=3
        )

        # "Paused" banner
        paused_banner = pt.Banner(
            f"[{string['gameplay']['paused']}]",
            BASE_SIZE * 2,
            scene.box.center[:],
            colors["pause_popup"],
            lifetime=0.6,
            animation_duration=0.3,
            tick_down=False
        )

        super(PauseEnsemble, self).__init__(
            buttons_list=[unpause_button, options_button, menu_button, exit_button],
            decoration_objects=[paused_banner],
            rect=scene.box,
            background=False,
            escape_button_index=0,
            add_tnt=True
        )


class MainMenu(Menu):

    def generate_buttons(self):
        buttons = [
            # Continue button:
            Button(
                text=[string['menu']['continue']],
                rect=DEFAULT_BUTTON_RECT,
                action=hd.SceneHandler.active.load_save,
                action_parameters=[hd.SkirmishSceneHandler],
                kb_index=0
            ),

            # Skirmish button
            Button(
                text=[string['menu']['skirmish']],
                rect=DEFAULT_BUTTON_RECT,
                action=self.scene.generate_menu_popup,
                action_keywords={
                    "menu_class": Difficulty,
                    "keywords": {
                        "action": self._start_skirmish,
                        "locked_from": PROGRESS["max_skirmish_beaten"] + 1
                    }
                },
                kb_index=1
            ),

            # Tutorial button
            Button(
                text=[string['menu']['tutorial']],
                rect=DEFAULT_BUTTON_RECT,
                action=self.scene.request_new_handler,
                action_keywords={
                    "scene_handler": hd.TutorialSceneHandler
                },
                kb_index=2
            ),

            # Options button:
            Button(
                text=[string['menu']['options']],
                rect=DEFAULT_BUTTON_RECT,
                action=self.scene.generate_menu_popup,
                action_keywords={"menu_class": Options},
                kb_index=3
            ),

            # Exit button
            Button(
                text=[string['menu']['exit']],
                rect=DEFAULT_BUTTON_RECT,
                action=self.scene.generate_menu_popup,
                action_keywords={
                    "menu_class": RUSureMenu,
                    "keywords": {
                        "title": string["menu"]["confirm_exit"],
                        "confirm_text": string['menu']['confirmed_exit'],
                        "action": exit_game
                    }
                },
                kb_index=4
            )
        ]

        # Check if there is a savefile; disable Continue button if not
        save = load_json('saved.json', 'progress')
        if save.get('type', None) != 'skirmish':
            buttons[0].disabled = True

        return buttons

    def __init__(self, scene, web_prompt=False):
        # Work within scene:
        self.scene = scene

        text = string["game_title"]
        decorated_rows = [[row, colors["inventory_title"]] for row in frame_text([text], style='┏━┓┗┛┃').splitlines()]
        row_length = len(decorated_rows[0][0])
        decorated_rows.append([string["game_subtitle"].rjust(row_length), colors["inventory_description"]])
        title_surface = ascii_draw_rows(BASE_SIZE, decorated_rows)

        super(MainMenu, self).__init__(
            self.generate_buttons(),
            reposition_buttons=(3, 2),
            background=True,
            title_surface=title_surface,
            add_tnt=True
        )

        self.web_prompt = web_prompt and not PROGRESS["disable_web_prompt"]

    def _start_skirmish(self, tier):
        self.scene.request_new_handler(scene_handler=hd.SkirmishSceneHandler, args=[tier])

    def display(self, mouse_v, active=True):
        # Add a web prompt menu on top of self if asked to
        if self.web_prompt:
            self.scene.menus.append(BrowserPrompt())
            self.web_prompt = False
            active = False

        return super(MainMenu, self).display(mouse_v, active)


class Victory(Menu):
    def __init__(
            self,
            scene,
            next_level_text=None,
            next_level_action=None,
            next_level_parameters=None,
            next_level_keywords=None,
            victory_text=None
    ):

        prompt_in_menu = not isinstance(hd.SceneHandler.active, hd.TutorialSceneHandler)

        # Modify savefile to be next level
        if hd.SceneHandler.active.tier < 4:
            hd.SceneHandler.active.save(next_level=True)
        else:
            # At Tier 4, character must be hall of famed instead of save
            wipe_save()

        # Stop theme music, play sound:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        play_sound('level_clear', 1)

        index = 0
        if next_level_text is not None:
            # Next level button:
            next_level_button = Button(
                text=[next_level_text],
                rect=DEFAULT_BUTTON_RECT,
                action=next_level_action,
                action_parameters=next_level_parameters,
                action_keywords=next_level_keywords,
                kb_index=index
            )
            index += 1
        else:
            next_level_button = None

        # Main menu button:
        # If there is no 'Next level' action saved, return to main menu does not require confirmation
        main_menu_action = {
            'action': scene.generate_menu_popup,
            'action_keywords': {
                "menu_class": RUSureMenu,
                "keywords": {
                    "title": string["menu"]["confirm_menu"],
                    "confirm_text": string['menu']['confirmed_menu'],
                    "action": scene.request_new_handler,
                    "action_parameters": [hd.MainMenuSceneHandler],
                    "action_keywords": {"kwargs": {"web_prompt": prompt_in_menu}}
                }
            }
        } if next_level_button is not None else {
            'action': scene.request_new_handler,
            "action_parameters": [hd.MainMenuSceneHandler],
            "action_keywords": {"kwargs": {"web_prompt": prompt_in_menu}}
        }

        menu_button = Button(
            text=[string['menu']['main']],
            rect=DEFAULT_BUTTON_RECT,
            kb_index=index,
            **main_menu_action
        )
        index += 1

        # Quit button
        exit_button = Button(
            text=[string['menu']['exit']],
            rect=DEFAULT_BUTTON_RECT,
            action=scene.generate_menu_popup,
            action_keywords={
                "menu_class": RUSureMenu,
                "keywords": {
                    "title": string["menu"]["confirm_exit"],
                    "confirm_text": string['menu']['confirmed_exit'],
                    "action": exit_game
                }
            },
            kb_index=index
        )

        buttons_list = [next_level_button, menu_button, exit_button] if next_level_button is not None else \
            [menu_button, exit_button]

        # Form victory surface for title:
        # 1. Victory statement surface
        victory_string = (victory_text or random.choice(string['gameplay']['scene_clear'])).ljust(15)
        statement_surface = ascii_draw(BASE_SIZE * 2, victory_string, colors['inventory_better'])
        # 2. Form killed monsters list surface
        if scene.dead_characters:
            killed_monsters_count = dict()
            for enemy in scene.dead_characters:
                killed_monsters_count[enemy.class_name] = killed_monsters_count.get(enemy.class_name, 0) + 1

            colored_header_row = [[string["gameplay"]["monster_list"].ljust(20), colors["inventory_text"]]]

            content_rows = frame_text(
                [
                    f"{key_value[0]}: {key_value[1]}".rjust(31)
                    for key_value in
                    sorted(killed_monsters_count.items(), key=lambda x: -x[1])
                ],
                '━━━━━ '
            )

            colored_content_rows = [[row, colors["inventory_text"]] for row in content_rows.splitlines()]

            # Add stats rows:
            combo = f'{scene.max_combo}{"!" * (min(3, scene.max_combo // 23))}'
            time = f'{scene.timer // 60:.0f}m{int(scene.timer % 60):.0f}.{str(scene.timer % 1)[2:4]}s'
            damage = f'{scene.player_damage:,.0f}'
            dps = f'{scene.player_damage / scene.timer:.2f} {string["gameplay"]["victory_stats"]["dps"]}'
            stats_rows = [
                [f'{string["gameplay"]["victory_stats"]["time"]}: {time}', colors["inventory_text"]],
                [f'{string["gameplay"]["victory_stats"]["combo"]}: {combo}', colors["inventory_text"]],
                [f'{string["gameplay"]["victory_stats"]["damage"]}: {damage} ({dps})', colors["inventory_text"]],
                [f'{string["gameplay"]["victory_stats"]["deaths"]}: {scene.player_deaths}', colors["inventory_text"]]
            ]

            killed_monsters_surface = ascii_draw_rows(BASE_SIZE, colored_header_row + colored_content_rows + stats_rows)

        else:
            killed_monsters_surface = s((0, 0))

        total_title_surface = s(
            (
                max(statement_surface.get_width(), killed_monsters_surface.get_width()) + BASE_SIZE * 2,
                BASE_SIZE * (3 if scene.dead_characters else 2) + statement_surface.get_height() +
                killed_monsters_surface.get_height()
            ),
            pygame.SRCALPHA
        )
        total_title_surface.fill(self._background_color)
        frame_surface(total_title_surface, colors['inventory_text'])
        total_title_surface.blit(statement_surface, (BASE_SIZE, BASE_SIZE))
        total_title_surface.blit(killed_monsters_surface, (BASE_SIZE, BASE_SIZE * 2 + statement_surface.get_height()))

        super().__init__(
            buttons_list=buttons_list,
            title_surface=total_title_surface,
            reposition_buttons=(1, len(buttons_list)),
            escape_button_index=menu_button.kb_index,
            add_tnt=True
        )


class Defeat(Menu):

    def __init__(self, scene):
        # No cheating! Wipe savefile:
        wipe_save()

        # Stop theme music, play sound:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        play_sound('level_failed', 1)

        # Main menu button:
        menu_button = Button(
            text=[string['menu']['main']],
            rect=DEFAULT_BUTTON_RECT,
            action=scene.generate_menu_popup,
            action_keywords={
                "menu_class": RUSureMenu,
                "keywords": {
                    "title": string["menu"]["confirm_menu"],
                    "confirm_text": string['menu']['confirmed_menu'],
                    "action": scene.request_new_handler,
                    "action_parameters": [hd.MainMenuSceneHandler],
                    "action_keywords": {"kwargs": {"web_prompt": True}}
                }
            },
            kb_index=0
        )

        # Quit button
        exit_button = Button(
            text=[string['menu']['exit_ingame']],
            rect=DEFAULT_BUTTON_RECT,
            action=scene.generate_menu_popup,
            action_keywords={
                "menu_class": RUSureMenu,
                "keywords": {
                    "title": string["menu"]["confirm_exit"],
                    "confirm_text": string['menu']['confirmed_exit_ingame'],
                    "action": exit_game
                }
            },
            kb_index=1
        )

        buttons_list = [menu_button, exit_button]

        defeat_banner = pt.Banner(
            string['gameplay']['game_over'],
            BASE_SIZE * 2,
            v(scene.box.center) - v(0, scene.box.height // 3),
            colors["game_over"],
            lifetime=6,
            animation_duration=3,
            tick_down=False
        )

        super().__init__(
            buttons_list=buttons_list,
            decoration_objects=[defeat_banner],
            reposition_buttons=(1, 2),
            escape_button_index=menu_button.kb_index,
            add_tnt=True
        )


class Difficulty(Menu):
    def __init__(self, action, locked_from: int = None):

        button_list = []
        index = 0

        # Generate buttons for difficulty levels
        for difficulty in range(1, 5):
            button = Button(
                text=[f"{string['menu']['difficulty']}: {difficulty}"],
                action=action,
                rect=DEFAULT_BUTTON_RECT,
                action_keywords={"tier": difficulty},
                kb_index=index
            )

            index += 1
            button_list.append(button)
            if difficulty > (locked_from or 0):
                button.disabled = True

        # Generate back buton:
        button_rect = DEFAULT_BUTTON_RECT.copy()
        button_rect.width *= 2
        button_list.append(Button(
            text=[string["menu"]["back"]],
            action=self.fade,
            kb_index=index,
            rect=button_rect
        ))

        # Generate title:
        title_surface = ascii_draw(BASE_SIZE, string['menu']['difficulty_choose'], colors["inventory_title"])

        super().__init__(
            button_list,
            reposition_buttons=(index + 1, 1),
            background=True,
            title_surface=title_surface
        )


class LootHelp(Menu):
    _background_color = c(*colors["loot_card"], 255)

    def __init__(self):
        button_list = [Button(
            text=[string["menu"]["ok"]],
            rect=DEFAULT_BUTTON_RECT,
            action=self.fade,
            kb_index=0
        )]

        title = ascii_draw_rows(
            BASE_SIZE, [(entry, colors["inventory_title"]) for entry in string["tutorial"]["loot_help"]]
        )

        super(LootHelp, self).__init__(
            buttons_list=button_list,
            background=True,
            title_surface=title,
            reposition_buttons=(1, 1)
        )


class BrowserPrompt(Menu):
    _background_color = c(*colors["loot_card"], 255)

    def never(self):
        remove_browser_prompt()
        self.fade()

    def __init__(self):
        title = ascii_draw_cascaded(
            BASE_SIZE,
            string["menu"]["web_prompt"]["prompt"],
            colors["inventory_title"],
            WINDOW_SIZE[0] * 3 // 4
        )

        buttons_list = [
            # Never
            Button(
                text=[string["menu"]["web_prompt"]["never"]],
                rect=r(0, 0, DEFAULT_BUTTON_RECT.width*3//2, DEFAULT_BUTTON_RECT.height),
                action=self.never,
                kb_index=0
            ),

            # No
            Button(
                text=[string["menu"]["web_prompt"]["no"]],
                rect=r(0, 0, DEFAULT_BUTTON_RECT.width*3//2, DEFAULT_BUTTON_RECT.height),
                action=self.fade,
                kb_index=1
            ),

            # Yes
            Button(
                text=[string["menu"]["web_prompt"]["yes"]],
                rect=r(0, 0, DEFAULT_BUTTON_RECT.width*3//2, DEFAULT_BUTTON_RECT.height),
                action=wb.open,
                action_keywords={"url": RATING_URL},
                kb_index=2
            ),
        ]

        super().__init__(
            buttons_list=buttons_list,
            background=True,
            title_surface=title,
            reposition_buttons=(1, 3),
            escape_button_index=1
        )