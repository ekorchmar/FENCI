# todo:
#  LootOverlayHelp > mousehints
#  Main menu
# after tech demo:
# todo:
#  sparks in inventory when weapon is damaged
#  character portrait, stats and name in topleft
#  Dialogues

from base_class import *
from typing import Callable
from particle import Banner


class Inventory:
    slots_order = 'main_hand', 'off_hand', 'hat', 'backpack'

    def __init__(
            self,
            character: Character,
            rectangle: r = INVENTORY_SPACE,
            bg_color=colors["base"],
            foreground=DISPLAY_COLOR
    ):
        self.rect = rectangle
        self.character = character
        self.slot_rects = {}

        # Create basic surface:
        self.base = s(size=rectangle.size)
        self.base.fill(foreground)

        # Create spaces for inventory slots
        slot_x = 0
        for slot in self.slots_order:
            # Prepare rectangle for the weapon:
            slot_rect = r(slot_x, 0, self.rect.width//4, self.rect.height)
            self.slot_rects[slot] = slot_rect

            # Write name of the slot
            slot_name_surf = ascii_draw(BASE_SIZE//2, SLOT_NAMES[slot], colors["inventory_text"])
            slot_name_rect = slot_name_surf.get_rect(right=slot_x+slot_rect.width, top=0)
            self.base.blit(slot_name_surf, slot_name_rect)

            # Offset next rectangle
            slot_x += slot_rect.width

            # Draw a line along the right border
            pygame.draw.line(
                self.base,
                bg_color,
                v(slot_x, 0),
                v(slot_x, self.rect.height),
                BASE_SIZE // 6
            )

        # Form content on surface
        self.surface = None
        self.bars = {}
        self.update()

    def update(self):
        surface = self.base.copy()
        for slot in self.slots_order:

            content = self.character.slots[slot]
            if not content:
                continue

            #  1. Get a portrait of each weapon from each of character slots
            portrait = content.portrait(rect=self.slot_rects[slot])
            surface.blit(portrait, self.slot_rects[slot])

            # 2. Form a durability bar (backpacked equipment can not be damaged)
            if not slot == 'backpack':
                color = colors["inventory_durability"] if content.durability > 1 else colors["inventory_broken"]

                durability = Bar(
                    size=BASE_SIZE,
                    width=content.max_durability,
                    max_value=content.max_durability,
                    fill_color=color,
                    base_color=color,
                    show_number=False,
                    cache=False,
                    style=' ♥♡ '
                )
                bar_surf, bar_rect = durability.display(content.durability)
                bar_left = (self.slot_rects[slot].width - bar_rect.width)//2
                bar_rect.move_ip(bar_left + self.slot_rects[slot].left, BASE_SIZE//2 + 3)
                surface.blit(bar_surf, bar_rect)

            # 3. Write down weapon class and tier
            class_string = f'{content.builder["class"]}'
            class_surf = ascii_draw(BASE_SIZE // 2, class_string, colors["inventory_text"])
            class_rect = class_surf.get_rect(left=self.slot_rects[slot].left + BASE_SIZE//2)

            tier_string = f'Tier {content.tier}'
            tier_surf = ascii_draw(BASE_SIZE//2, tier_string, colors["inventory_text"])
            tier_rect = tier_surf.get_rect(bottomright=self.slot_rects[slot].bottomright)

            surface.blit(tier_surf, tier_rect)
            surface.blit(class_surf, class_rect)

        self.surface = surface

    def draw(self):
        return self.surface, self.rect


class LootOverlayHelp:
    def __init__(self, size=BASE_SIZE*3//4):
        # Get text
        top_text = ascii_draw(size, "CLOSE", c(colors["inventory_title"]))
        middle = ascii_draw(size, "EQUIP   STASH", c(colors["inventory_title"]))

        # Form surface
        s_size = middle.get_width(), top_text.get_height() * 2
        self.surface = s(s_size, pygame.SRCALPHA)

        # Blit everything:
        # todo: calculate dynamically depending on word length
        self.middle_v = v(s_size[0] // 2, s_size[1] * 3 // 4)
        self.surface.blit(top_text, top_text.get_rect(center=(s_size[0] // 2, s_size[1] // 4)))
        self.surface.blit(middle, middle.get_rect(center=self.middle_v))

    def draw(self, position):
        position_v = v(position)
        new_topleft = position_v - self.middle_v
        return self.surface, self.surface.get_rect(topleft=new_topleft)


class LootOverlay:
    def __init__(
            self,
            loot_list: list[Equipment],
            character: Character,
            rect: r = LOOT_SPACE,
            label_size: int = BASE_SIZE * 3 // 2,
            label: str = 'LOOT TIME!',
            offset: int = BASE_SIZE,
            appear_from: v = None,
            animation_time: float = 1.5,
            draw_shortcuts: bool = True
    ):
        self.loot_list = loot_list
        self.character = character
        self.offset = offset
        self.loot_dict = dict()
        self.show_neighbor_dict = dict()
        self.rect = rect
        self.draw_shortcuts = draw_shortcuts

        # Animations:
        self.appear_from = appear_from
        self.lifetime = 0
        self.animation_time = animation_time

        self.surface = s(LOOT_SPACE.size, pygame.SRCALPHA)
        self.surface.fill(c(*colors["loot_card"], 127))
        # Draw label:
        label_surf = ascii_draw(label_size, label, c(colors["inventory_better"]))
        self.label_rect = label_surf.get_rect(midtop=self.surface.get_rect().midtop)
        self.surface.blit(label_surf, self.label_rect)

        self.redraw_loot()

        # Draw frame:
        frame_surface(self.surface, colors["inventory_text"])

        # Display help:
        self.helper = LootOverlayHelp()

    def redraw_loot(self):
        # Draw loot cards:
        loot_card_count = len(self.loot_list)
        x_offset = self.offset
        y_offset = self.label_rect.height + self.offset
        x_offset_iteration = (self.rect.width - self.offset * 2 - loot_card_count * MAX_LOOT_CARD_SPACE.width) \
            // (loot_card_count - 1)

        card_index = 0
        for loot in self.loot_list:
            if self.character and self.character.slots[loot.prefer_slot]:
                compare_to = self.character.slots[loot.prefer_slot]
                if compare_to not in loot.loot_cards:
                    loot.loot_cards[compare_to] = LootCard(loot, compare_to)
            else:
                compare_to = None

            loot_card, loot_card_rect = loot.loot_cards[compare_to].draw(
                position=(x_offset, y_offset), x_key='left', y_key='top'
            )
            self.surface.blit(loot_card, loot_card_rect)

            # Update loot_neighbor_dict to collect options to display comparison loot
            leftside = x_offset < LOOT_SPACE.width * 0.5
            self.show_neighbor_dict[loot] = {
                "x_key": 'left' if leftside else 'right',
                "y_key": 'bottom',
                "position": v(loot_card_rect.bottomright) if leftside else v(loot_card_rect.bottomleft)
            }

            self.show_neighbor_dict[loot]["position"] += v(self.rect.topleft)
            self.show_neighbor_dict[loot]["position"] += v(self.offset, 0) if leftside else v(-self.offset, 0)

            # Draw shortcuts
            if self.draw_shortcuts:
                shortcurt_surface = ascii_draw(BASE_SIZE*2//3, NUMBER_LABELS[card_index], colors["inventory_title"])
                shortcut_rect = shortcurt_surface.get_rect(
                    topleft=v(loot_card_rect.topleft)+v(0.5*self.offset, 0.5*self.offset)
                )
                self.surface.blit(shortcurt_surface, shortcut_rect)

            # Offset loot_card_rect by parent surface topleft, to let clicks through
            loot_card_rect.move_ip(self.rect.left, self.rect.top)
            self.loot_dict[loot] = loot_card_rect
            x_offset += x_offset_iteration + loot_card_rect.width

            card_index += 1

    def draw(self):
        surface = self.surface.copy()
        # Blit cursor helper on self:
        cursor_v = v(pygame.mouse.get_pos()) - v(self.rect.topleft)
        surface.blit(*self.helper.draw(cursor_v))

        # If no appearance point is set, no animation is required
        if self.appear_from is None or self.lifetime >= self.animation_time:
            return surface, self.rect

        # Else, find new position and scaled size
        progress = self.lifetime / self.animation_time
        self.lifetime += FPS_TICK

        # Position:
        start_v = self.appear_from
        end_v = v(self.rect.center)
        current_v = v(start_v.x * (1-progress) + end_v.x * progress, start_v.y * (1-progress) + end_v.y * progress)

        # Size:
        current_size = int(self.rect.width * progress), int(self.rect.height * progress)

        surface = pygame.transform.smoothscale(surface, current_size)
        rect = surface.get_rect(center=current_v)

        return surface, rect

    def catch(self, position, mouse_state):
        # If animation is not finished, instantly complete it, and return no click
        if any(mouse_state) and self.lifetime < self.animation_time:
            self.lifetime = self.animation_time
            return None, None

        if not any(mouse_state):
            # Return loot, None slot
            for loot in self.loot_dict:
                if self.loot_dict[loot].collidepoint(position):
                    return loot, None

        for loot in self.loot_dict:
            if self.loot_dict[loot].collidepoint(position):
                if mouse_state[0]:
                    return loot, loot.prefer_slot
                elif mouse_state[2]:
                    return loot, 'backpack'

        return None, None

    def catch_index(self, index):
        # If animation is not finished, instantly complete it, and return no click
        if self.lifetime < self.animation_time:
            self.lifetime = self.animation_time
            return None, None

        try:
            loot = self.loot_list[index]
            return loot, loot.prefer_slot
        except IndexError:
            return None, None


class Indicator:
    def __init__(self, surface):
        self.surface = surface
        self.empty = s(self.surface.get_size(), pygame.SRCALPHA)
        self.value = False

    def set(self, value):
        self.value = value

    def draw(self, position=None):
        options = {}
        if position is not None:
            options["topleft"] = position

        if self.value:
            return self.surface, self.surface.get_rect(**options)

        return self.empty, self.surface.get_rect(**options)


class ProgressionBars:
    def __init__(
            self,
            content: dict[str, [Bar, Indicator]],
            draw_order: list[str],
            base_color=DISPLAY_COLOR,
            rect=LEVEL_BAR_SPACE,
            font_size=BASE_SIZE*2//3,
            offset=BASE_SIZE//3
    ):
        # Initiate a surface:
        self.surface = s(rect.size, pygame.SRCALPHA)
        self.rect = rect
        self.base_color = c(base_color)
        self.font_size = font_size
        self.offset = offset

        # Contents (Bars and Indicators)
        self.draw_order = draw_order
        self.content = content

    def update(self, values: list):
        self.surface.fill(self.base_color)
        # Draw from top and right:
        x, y = self.rect.width - self.offset, self.offset

        for i in range(len(self.draw_order)):
            name = self.draw_order[i]
            graphic = self.content[name]
            value = values[i]

            if isinstance(graphic, Bar):
                surface, rect = graphic.display(value)
                rect.right, rect.top = x, y
                self.surface.blit(surface, rect)
                name_x = x-rect.width

                # Draw name
                name_surface = ascii_draw(self.font_size, f'{name}:', c(colors['inventory_durability']))
                name_rect = name_surface.get_rect(right=name_x, top=y)
                self.surface.blit(name_surface, name_rect)

            elif isinstance(graphic, Indicator):
                graphic.set(value)
                surface, rect = graphic.draw()
                rect.right, rect.top = x, y
                self.surface.blit(surface, rect)

            else:
                raise TypeError(f"Can't handle contents in progression bar:{graphic}")

            y += rect.height

    def draw(self):
        return self.surface, self.rect


class HeldMouse:
    def __init__(self, execute, options_dict: dict, text: str, size=BASE_SIZE, timer=1, color=colors["crit_kicker"]):
        # Base:
        text_surface = ascii_draw(size, text, color)
        self.base_surface = s((text_surface.get_width(), text_surface.get_height() * 4), pygame.SRCALPHA)
        self.base_surface.blit(text_surface, (0, 0))

        # Drawing constants:
        self.size = size
        self.color = color

        # Drawing position:
        self.center_offset = v(0, 0)
        self.bound_rect = r(
            text_surface.get_width()//2 - size,
            text_surface.get_height()//2 + size,
            size*2,
            size*2
        )

        # Time count:
        self.held_timer = 0
        self.max_timer = timer

        # When completed:
        self.execute = execute
        self.options = options_dict

    def draw(self, position: v):
        surface = self.base_surface.copy()
        pygame.draw.arc(
            surface,
            self.color,
            self.bound_rect,
            start_angle=math.pi*(-0.5 + (2 * self.held_timer/self.max_timer)),
            stop_angle=-math.pi/2,
            width=self.size//4
        )
        rect = surface.get_rect(center=position)
        rect.move_ip(self.center_offset)
        return surface, rect

    def hold(self):
        """Return True or statement result when completed"""
        if self.held_timer >= self.max_timer:
            return self.execute(**self.options) or True

        self.held_timer += FPS_TICK
        return False


class Button:
    def __init__(
            self,
            text: list[str],
            rect: r,
            action: Callable,
            action_parameters: list = None,
            action_keywords: dict = None,
            size: int = BASE_SIZE,
            mouse_over_text: list[str] = None,
            kb_index: int = None
    ):
        # Basis:
        self.text = text
        self.mouse_over_text = mouse_over_text or self.text
        self.action = action
        self.action_parameters = action_parameters or list()
        self.action_keywords = action_keywords or dict()

        # Activation handles:
        self.rect = rect
        self.kb_index = kb_index

        # Create surfaces:
        # Text content:
        text_surface = ascii_draw_rows(size, [[row, colors["inventory_text"]] for row in self.text])
        text_rect = text_surface.get_rect(center=v(self.rect.center)-v(self.rect.topleft))
        text_surface_moused = ascii_draw_rows(size, [[row, colors["inventory_text"]] for row in self.mouse_over_text])
        text_moused_rect = text_surface_moused.get_rect(center=v(self.rect.center)-v(self.rect.topleft))

        # Unmoused:
        self.surface = s(rect.size, pygame.SRCALPHA)
        self.surface.fill(c(colors["loot_card"]))
        frame_surface(self.surface, colors["inventory_text"])
        self.surface.blit(text_surface, text_rect)

        # If index is specified, add it to unmoused surface:
        if kb_index is not None:
            index_surface = ascii_draw(size * 2 // 3, NUMBER_LABELS[kb_index], colors["inventory_title"])
            self.surface.blit(index_surface, (BASE_SIZE//2, BASE_SIZE//2))

        # Moused:
        self.moused_over_surface = self.surface.copy()
        self.moused_over_surface.fill(c(colors["inventory_description"]))
        frame_surface(self.moused_over_surface, colors["inventory_text"])
        self.moused_over_surface.blit(text_surface_moused, text_moused_rect)

    def draw(self, moused_over: bool):
        return self.moused_over_surface if moused_over else self.surface, self.rect

    def activate(self):
        self.action(*self.action_parameters, **self.action_keywords)


class Menu:
    """Stolen from BamboozleChess."""

    def __init__(
            self,
            buttons_list: list[Button],
            rect: r = None,
            decoration_objects: list[Banner] = None,
            background: bool = False,
            offset: int = BASE_SIZE,
            reposition_buttons: tuple = None,
            escape_button_index: int = None,
            title_surface: s = None
    ):

        # Remember position and contents:
        self.title = title_surface
        self.rect = rect
        self.buttons_list = buttons_list
        self.dimensions = reposition_buttons
        self.offset = offset
        self.decoration_objects = decoration_objects or list()
        self.fading = False

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

            self.rect = r(
                left-self.offset,
                top-self.offset,
                right-left+self.offset*2,
                bottom-top+self.offset*2
            )

        # Draw background if asked to:
        self.background = s(self.rect.size, pygame.SRCALPHA)
        if background:
            self.background.fill(c(*colors["loot_card"], 127))
            frame_surface(self.background, colors["inventory_text"])
        else:
            self.background.fill([0, 0, 0, 0])
            self.background.set_alpha(0)

        # Modify rect if it is not supplied

        if self.title:
            title_rect = self.title.get_rect(midtop=(self.rect.width//2, self.offset))
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
        buttons_box.center = v(self.rect.center) - v(self.offset//2, self.offset//2) if self.rect \
            else (WINDOW_SIZE[0]//2, WINDOW_SIZE[1]//2)

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

        return draw_order

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

    @staticmethod
    def process(button):
        button.activate()

    def fade(self):
        """Remove all buttons, cause all banners to fade"""
        self.buttons_list = []
        self.fading = True


class OptionsMenu(Menu):
    def fade(self):
        # Write options dict to json file
        with open(os.path.join('options', 'options.json'), 'w') as options_json:
            json.dump(OPTIONS, options_json)
        super(OptionsMenu, self).fade()

    def toggle(self, key):
        # Toggle an option and cause redrawing all buttons
        OPTIONS[key] = not OPTIONS[key]
        self.redraw()
        if key == 'fullscreen':
            update_screen()

    def generate_buttons(self):
        buttons_list = []
        i = 0
        for key in OPTIONS:
            option_state_text = string['menu']['option_contents']["bool"]["True" if OPTIONS[key] else "False"]
            button_text = f"{string['menu']['option_contents'][key]}: {option_state_text}"
            button_rect = DEFAULT_BUTTON_RECT.copy()
            button_rect.width *= 2
            buttons_list.append(Button(
                text=[button_text],
                action=self.toggle,
                action_keywords={'key': key},
                rect=button_rect,
                kb_index=i
            ))
            i += 1

        # Add close button
        buttons_list.append(Button(
            text=[string["menu"]["back"]],
            action=self.fade,
            rect=DEFAULT_BUTTON_RECT,
            kb_index=i
        ))

        return buttons_list

    def __init__(self):
        super(OptionsMenu, self).__init__(
            self.generate_buttons(),
            reposition_buttons=(4, 2),
            background=True,
            title_surface=ascii_draw(BASE_SIZE*2, string["menu"]["options"].upper(), colors["inventory_title"])
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
