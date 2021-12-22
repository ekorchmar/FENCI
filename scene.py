# todo:
# After tech demo
# todo:
#  Split options into submenus; add options for: SFX volume;
#  Store each completed level in progress/victory.json
#  Procedure to querry victory.json for top DPS and lowest time per level tier and type
#  bleeding contributes to player_damage
#  tile generation
#  achievements
#  ?? F causes taunt, forcing closest enemy to charge
#  scenario feeds dict with debug info into scene for display_debug
#  Player.fate: dict to remember player choices for future scenario, also displayed in stat card
# todo: Add lightning effect to character spawn
#  sparks in inventory when weapon is damaged
#  Dialogues

import base_class as b
import particle as pt
import equipment as eq
import boss as bs
import menu as mn
import handler as hd
from primitive import *

# Display FPS counters(initial state):
_fps_querried_time = 1000
_fps_count = ascii_draw(40, '0', (255, 255, 0))


# Scene class draws everything and processess game physics
class Scene:

    def __init__(
            self,
            player,
            window,
            bounds,
            enemies=None,
            progression=None,
            decorative: bool = False,
            custom_surface: s = None
    ):
        self.collide_this_frame = False
        self.timer = 0
        self.window = window
        self.box = bounds
        self.decorative = decorative

        # Increase field size by shake range in all directions
        if custom_surface is None:
            self.field = s(v(bounds.size) + 2 * SHAKER_BUFFER)
            self.field.fill(DISPLAY_COLOR)
        else:
            self.field = s(v(custom_surface.get_size()) + 2 * SHAKER_BUFFER)
            self.field.blit(custom_surface, SHAKER_BUFFER)

        # Buffered field rect:
        self.field_rect = r(
            SHAKE_RANGE,
            SHAKE_RANGE,
            self.field.get_width() - 2 * SHAKE_RANGE,
            self.field.get_height() - 2 * SHAKE_RANGE
        )

        # Camera position:
        self.camera: v = v(self.field_rect.center)

        # Calculated conversion between point on field and in window:
        self.conversion_v: v = v()

        # Remember player:
        self.player = player

        # Put player in characters list
        self.characters = []
        if self.player:
            self.characters.append(self.player)
        if enemies:
            self.characters.extend(enemies)

        # Create a combo counter and stats for player
        self.combo_counter = None
        self.introduce_combo()

        self.max_combo = 0
        self.player_deaths = 0
        self.player_damage = 0

        # Landing animation requires scene to remember character states:
        self.character_states = {char: char.state for char in self.characters}

        # Order collision groups so that player is processed first:
        self.collision_groups = [char.collision_group for char in self.characters]
        self.collision_groups.sort()

        # Updated with player input
        self.pointer: v = v()
        self.display_debug = False
        self.paused = False
        self.keyboard = pygame.key.get_pressed()
        self.held_mouse: [None, HeldMouse] = None

        # Store applicable weapons for collision detection
        self.colliding_weapons = {}
        self.log_weapons()

        # Store and animate killed characters
        self.dead_characters = []

        # Log how many enemies remain on screen each time an enemy is killed
        # This tells SceneHandler if player clears enemies too fast, so more enemies should be spawned at once
        self.enemies_count_on_death = []

        # Store damage kickers and other particles
        self.particles = []
        self.enemy_direction = None if self.player is None else pt.EnemyDirection(self.player, self.characters)

        # Store display for level progress:
        self.progression = progression

        # Reserved for pause popups and banners:
        self.pause_popups = None
        self.loot_overlay = None
        self.draw_helper = False
        self.draw_group_append = []

        # bs.Boss HP bar and name:
        self.boss_bar = None
        self.boss_bar_center = None
        self.boss_name = None

        # Support drawing buttons and menus:
        self.menus = []

        # Property as shortcut for SceneHandler to know when to hand over; scene can not do it by itself
        self.new_sh_hook = None

        # Create own shaker for camera shake:
        self.shaker = b.Shaker()
        self.shake_v = v()

    def introduce_combo(self):
        if self.player is None:
            self.combo_counter = None
        else:
            self.combo_counter = pt.ComboCounter(
                scene=self,
                position=v(self.box.topright) + v(-BASE_SIZE * 2.5, BASE_SIZE * 2)
            )
            self.player.combo_counter = self.combo_counter

    def log_weapons(self):
        for character in self.characters:
            self.colliding_weapons[character] = [
                character.slots[slot] for slot in character.weapon_slots
                if character.slots[slot].hitbox()
            ]

        if self.player and self.player.inventory:
            self.player.inventory.update()

    def alert_ai(self, victim):
        for character in filter(lambda x: x.ai is not None and not isinstance(x, bs.Boss), self.characters):
            # React to death:
            if victim in self.dead_characters:

                if isinstance(victim, bs.Boss):
                    character.ai.morale = 0.0
                else:
                    # Rigid AI gains less morale, Cowardly AI loses more
                    character.ai.morale += 0.4 * character.ai.flexibility \
                        if victim.collision_group != character.collision_group \
                        else -0.2 - 0.1 * character.ai.courage

                    # Respect boundaries
                    character.ai.morale = min(character.ai.morale, 1.0)
                    character.ai.morale = max(character.ai.morale, 0.0)

            character.ai.fight_or_flight(victim)

    def update_input(self):

        # Convert mouse target:
        self.pointer = b.MouseV.instance.get_v(self.conversion_v)
        b.MouseV.instance.remember(self.pointer)

        spacebar, debug, wheel, escape = False, False, False, False
        number_keys = [False] * 9

        for event in pygame.event.get():  # User did something

            if event.type == pygame.QUIT:  # If user closed the window
                hd.SceneHandler.active.complete()

            if event.type == pygame.MOUSEWHEEL:
                wheel = True

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE and not self.loot_overlay:
                    escape = True

                if event.key == pygame.K_TAB:
                    self.display_debug = not self.display_debug

                if event.key == pygame.K_SPACE:
                    spacebar = True

                if event.key == pygame.K_f:
                    debug = True

                # Get pressed number keys
                for index_key in NUMBER_CODES:
                    number_keys[index_key[0]] = (event.key == index_key[1])

        b.MouseV.instance.update_buttons()
        keyboard = pygame.key.get_pressed()

        # Digest held buttons input:
        movement = keyboard[pygame.K_w], keyboard[pygame.K_a], keyboard[pygame.K_s], keyboard[pygame.K_d]
        shift = keyboard[pygame.K_LSHIFT]

        self.draw_helper = False

        # Debug:
        if debug:
            if isinstance(hd.SceneHandler.active, hd.TutorialSceneHandler) and not self.menus:
                hd.SceneHandler.active.next_stage()

            elif self.player and self.player in self.characters:
                self.echo(self.player, "Let's make some noise!", colors["lightning"])

        # Normal input processing:
        if not self.paused and not self.loot_overlay:
            # Set cursor shape:
            pygame.mouse.set_system_cursor(pygame.SYSTEM_CURSOR_CROSSHAIR)

            # Toggle pause if no menus are drawn
            if escape and not self.menus:
                self.toggle_pause()
                # Prevent Pause menu instantly closing
                escape = False

            # Start channeling flip
            if spacebar and self.player in self.characters:

                # If character is hurt, flip is instant:
                if self.player.immune_timer > 0:
                    self.player.flip()
                else:
                    self.player.channel(self.player.flip_time, self.player.flip, {})

            # Start channeling weapon switch
            if wheel and self.player in self.characters and self.player.slots["backpack"]:
                # Duration depends on weight of backpack weapon
                switch_time = self.player.flip_time * self.player.slots["backpack"].weight * 0.1
                self.player.channel(switch_time, self.player.backpack_swap, {"scene": self})

            # Feed input to characters
            for char in self.characters:
                if char in self.dead_characters:
                    continue

                # Feed input to player character:
                if char is self.player:
                    # Move:
                    char_direction = kb_move(movement)
                    speed_limit = 1.0

                    # Use:
                    if not self.menus:
                        for i in range(3):
                            if b.MouseV.instance.mouse_state[i]:
                                continuous = b.MouseV.instance.last_mouse_state[i]
                                self.player.use(PLAYER_SLOTS[i], continuous)

                    # Aim:
                    aiming = self.pointer
                # Listen to AI choices:
                else:
                    char_direction, aiming = char.ai.execute()
                    speed_limit = char.ai.speed_limit

                char.update(aiming, disable_weapon=shift)
                char.move(char_direction, self, limit=speed_limit)

            # Check character states to check if any character landed to spawn particles:
            new_character_states = {char: char.state for char in self.characters}
            for char in new_character_states:
                try:
                    if new_character_states[char] not in AIRBORNE and self.character_states[char] in AIRBORNE:
                        # Shake up:
                        if OPTIONS["screenshake"]:
                            self.shaker.add_shake(0.25 * char.size / BASE_SIZE)

                        # Play sound:
                        play_sound('landing', 0.5 * char.size / BASE_SIZE)

                        # Spawn dust clouds
                        for _ in range(int(char.weight * 0.02)):
                            self.particles.append(pt.DustCloud(random.choice(char.hitbox)))
                except KeyError:
                    continue
            self.character_states = new_character_states

            # Spawn blood particles for continiously bleeding characters
            for bleeding_character in filter(lambda x: x.bleeding_timer > 0, self.characters):
                # On average, 10 droplets per second
                if isinstance(bleeding_character, b.Character) and random.random() < 10 * FPS_TICK:
                    droplet = pt.Droplet(
                        position=v(bleeding_character.position),
                        character=bleeding_character,
                        spawn_delay=0
                    )
                    self.particles.append(droplet)

        # Allow player to instantly switch weapons if loot overlay is displayed:
        elif wheel and self.loot_overlay:
            self.player.backpack_swap(scene=self)
            self.loot_overlay.redraw_loot()

        # Process clicks and keypresses on loot overlay
        elif self.loot_overlay and not self.menus:
            if self.loot_overlay.rect.collidepoint(b.MouseV.instance.v):

                # Middle click closes overlay
                if b.MouseV.instance.mouse_state[1]:
                    self._close_and_repair()

                else:
                    # Draw help around the mouse:
                    self.draw_helper = True

                    # Pass mouse click to loot overlay:
                    result = self.loot_overlay.catch(b.MouseV.instance.v, b.MouseV.instance.mouse_state)
                    # Prevent accidental mouse holds
                    if all(result) and b.MouseV.instance.input_changed():
                        self._from_loot_overlay(*result)

                    # If any loot cards are moused over and there is a valid comparison, draw a loot card nearby
                    elif result[0]:
                        display_card_position = self.loot_overlay.show_neighbor_dict[result[0]]
                        # Check if we have a comparable weapon equipped:
                        own_equipment = self.player.slots[result[0].prefer_slot]
                        if own_equipment:
                            card_surface, card_rect = (own_equipment.loot_cards[None].draw(**display_card_position))
                            # Mark 'Equipped':
                            card_surface = card_surface.convert_alpha()
                            card_surface.blit(
                                ascii_draw(BASE_SIZE * 2 // 3, string["equipped"], colors["inventory_title"]),
                                (self.loot_overlay.offset * 0.5, self.loot_overlay.offset * 0.5)
                            )
                            self.draw_group_append.append([card_surface, card_rect])

                # Fully heal player no matter the picked option:
                self.player.hp, self.player.stamina = self.player.max_hp, self.player.max_stamina

            if any(number_keys):
                result = self.loot_overlay.catch_index(number_keys.index(True))
                self._from_loot_overlay(*result)

        # Allow dropping weapons in pause or loot overlay:
        if (
                self.player and
                self.player.inventory and
                (self.loot_overlay or self.paused) and
                self.player.inventory.rect.collidepoint(b.MouseV.instance.v)
        ):

            # Can't drop last damaging weapon:
            not_last_weapon = len(list(filter(
                lambda x: self.player.slots[x],
                self.player.weapon_slots + ['backpack']
            ))) > 1

            if not_last_weapon and self.held_mouse is None and b.MouseV.instance.mouse_state[0]:

                # Spawn a held_mouse object that will drop from inventory
                for slot in self.player.inventory.slot_rects:

                    modified_target = b.MouseV.instance.get_v(
                        start_v=(self.player.inventory.rect.left, self.player.inventory.rect.top))

                    if (
                            self.player.inventory.slot_rects[slot].collidepoint(modified_target) and
                            self.player.slots[slot]
                    ):
                        self.held_mouse = HeldMouse(
                            execute=self.item_drop,
                            options_dict={
                                "character": self.player,
                                "dropped_item": self.player.slots[slot],
                                "slot": slot
                            },
                            text=f"{string['inventory_drop']} {string['slot_names'][slot].upper()}"
                        )

        # Handle procession and deletion of HeldMouse object:
        if self.held_mouse is not None:
            if not b.MouseV.instance.mouse_state[0] or self.held_mouse.hold():
                self.held_mouse = None

        # Handle most recent displayed menu:
        if self.menus:
            # Set cursor shape:
            pygame.mouse.set_system_cursor(pygame.SYSTEM_CURSOR_ARROW)

            if b.MouseV.instance.mouse_state[0] and not b.MouseV.instance.last_mouse_state[0]:
                self.menus[-1].collide_button(b.MouseV.instance.v)

            elif any(number_keys):
                self.menus[-1].index_button(number_keys.index(True))

            elif escape:
                escape_index = self.menus[-1].escape_button_index
                self.menus[-1].index_button(escape_index)

            # If menu particles and buttons are empty, despawn it
            if self.menus[-1].exhausted:
                self.menus.pop(-1)

        # Handle buttons in pause ensemble, if no menus are drawn:
        elif self.pause_popups:
            # Set cursor shape:
            pygame.mouse.set_system_cursor(pygame.SYSTEM_CURSOR_ARROW)

            if b.MouseV.instance.mouse_state[0] and not b.MouseV.instance.last_mouse_state[0]:
                self.pause_popups.collide_button(b.MouseV.instance.v)

            elif any(number_keys):
                self.pause_popups.index_button(number_keys.index(True))

            elif escape:
                escape_index = self.pause_popups.escape_button_index
                self.pause_popups.index_button(escape_index)

        # Prevent event queue overflow:
        # pygame.event.pump()

    def _close_and_repair(self):
        # Find the least damaged equipment to repair
        least_damaged = None
        least_damage = 100

        random_order = list(self.player.slots.keys())
        random.shuffle(random_order)
        for slot in random_order:
            equipped = self.player.slots[slot]

            # Can't repair completely broken equipment
            if not equipped or equipped.durability == 0:
                continue

            damage = equipped.max_durability - equipped.durability
            if least_damage > damage > 0:
                least_damaged = equipped
                least_damage = damage

        # Repair durability to least damaged; spawn a banner
        if least_damaged is not None:
            least_damaged.durability += 1
            text = f"{string['loot']['repair']} {least_damaged.name}!"

            # Update loot cards in the scene:
            least_damaged.redraw_loot()
            self.log_weapons()

        else:
            text = string["loot"]["skip"]

        if self.loot_overlay.banner:
            self.report(text, colors["inventory_better"])

        # Close loot overlay
        play_sound('button', 1)
        self.loot_overlay = None

    def _from_loot_overlay(self, item, slot):
        if not item:
            return

        dropped = self.player.equip(item, slot)
        if dropped:
            self.item_drop(
                character=self.player,
                dropped_item=dropped,
                equip=False
            )
        item.reset(self.player, reposition=True)
        self.log_weapons()

        # Show info banner:
        if self.loot_overlay.banner:
            text = f"{string['loot']['backpack1']} {item.name} {string['loot']['backpack2']}" \
                if slot == "backpack" else f"{string['loot']['equip']} {item.name}!"

            self.report(text, colors["inventory_better"])
        self.loot_overlay = None

    def draw(self):
        # Draw bg:
        self.window.fill(colors["base"])

        # Find a center of field of view, centered around player:
        fov_rect = self.box.copy()
        # Follow player:
        if self.player:
            fov_rect.center = self.camera.lerp(self.player.position, CAMERA_SPEED)
        fov_rect = fov_rect.clamp(self.field_rect)
        self.camera = v(fov_rect.center)
        self.conversion_v = v(self.box.topleft) - v(fov_rect.topleft)

        # Add shake:
        fov_rect.move_ip(self.shake_v)

        draw_groups = {
            "field": list(),
            "box": list()
        }

        # Draw all characters on field
        for character in self.characters:

            drawn_pairs = character.draw(freeze=self.paused, no_bars=self.decorative)

            draw_groups["field"].extend(drawn_pairs)

            # Spawn dust clouds under rolling or ramming characters
            try:
                if character.hitbox and character.rolling > 0 or character.ramming:
                    # Spawn on average 10/s for standard size:
                    if random.random() < 10 * FPS_TICK * character.size / BASE_SIZE:
                        self.particles.append(pt.DustCloud(random.choice(character.hitbox)))
            except AttributeError:
                pass

        # Test if any enemy is visible this frame:
        if self.player:
            self.player.sees_enemies = False
            enemies = list(filter(lambda char: char.collision_group != self.player.collision_group, self.characters))
            for enemy in enemies:
                for rect in enemy.hitbox:
                    if rect.colliderect(fov_rect):
                        self.player.sees_enemies = True
                        break
                if self.player.sees_enemies:
                    break

            if enemies and not self.player.sees_enemies:
                self.enemy_direction.find_closest_enemy(self.characters)
                drawn = self.enemy_direction.draw()
                if drawn:
                    surface, rect = drawn
                    draw_groups["field"].append((surface, rect.clamp(fov_rect)))

        # Draw damage kickers, dead bodies and other particles:
        exhausted = []
        for particle in self.particles:

            # Remains are returning lists of tuples:
            if isinstance(particle, pt.Remains):
                drawn_remains = particle.draw(pause=self.paused)
                draw_groups["field"].extend(drawn_remains)

            # Everything else returns tuples or nothing:
            else:
                drawn = particle.draw(pause=self.paused)
                if drawn:
                    # Draw on field if particle is shakeable, on box otherwise:
                    canvas = "field" if particle.shakeable else "box"
                    surf, rect = drawn
                    # Some informative particles must always stay visible
                    if particle.clampable:
                        rect.clamp_ip(fov_rect)
                    draw_groups[canvas].append(drawn)

                    # If particle is outside bounds and not a pt.Banner, despawn it
                    # Commented: causes more headache than performance boost
                    # if not (drawn[1].colliderect(fov_rect) and not particle.shakeable):
                    #    print(f"Warning: despawning {particle} out of bounds")
                    #    exhausted.append(particle)

            if particle.lifetime <= 0:
                exhausted.append(particle)

        for particle in set(exhausted):
            self.particles.remove(particle)

        # Draw UI elements:
        if OPTIONS["screenshake"] >= 1:
            ui_shake = self.shake_v * 0.5
        else:
            ui_shake = self.shake_v

        if self.player:
            for ui in (self.player.inventory, self.progression, self.combo_counter):
                if not ui:
                    continue

                drawn = ui.draw()
                draw_groups['box'].append((drawn[0], v(drawn[1][:2]) - ui_shake))

        # Draw bs.Boss bar:
        if self.boss_bar is not None:
            # Draw boss banner:
            draw_groups['box'].append(self.boss_name.draw())

            # Animate boss HP bar appearance:
            boss = [char for char in self.characters if isinstance(char, bs.Boss)][0]
            bar, rect = self.boss_bar.display(boss.hp)
            bar.set_alpha(int(lerp(
                values_range=(0, 255),
                progression=(self.boss_name.max_lifetime - self.boss_name.lifetime) / self.boss_name.animation_duration
            )))

            rect.center = self.boss_bar_center
            draw_groups['box'].append((bar, rect))

        # Draw pause surfaces
        if self.pause_popups:
            pause_ensemble = self.pause_popups.display(b.MouseV.instance.v, active=not bool(self.menus))
            if pause_ensemble:
                draw_groups['box'].extend(pause_ensemble)
            else:
                self.pause_popups = None

        if self.loot_overlay:
            draw_groups['box'].append(self.loot_overlay.draw())

            # Draw helper:
            if self.draw_helper:
                draw_groups['box'].extend(self.loot_overlay.helper.draw())

        # Draw menus:
        mouse_on_button = False
        expired_menus = []
        if self.menus:
            for menu in self.menus:
                draw_groups['box'].extend(menu.display(mouse_v=b.MouseV.instance.v, active=menu is self.menus[-1]))
                mouse_on_button = mouse_on_button or any(
                    button.rect.collidepoint(b.MouseV.instance.v) for button in menu.buttons_list
                )
                if not menu.buttons_list and not menu.decoration_objects:
                    expired_menus.append(menu)

        for menu in expired_menus:
            self.menus.remove(menu)

        # If mouse is hovering over the scene, show equipped weapons and stat cards
        # Unless any of the buttons are moused over in menus or pause popup:
        if self.pause_popups:
            mouse_on_button = mouse_on_button or any(
                button.rect.collidepoint(b.MouseV.instance.v) for button in self.pause_popups.buttons_list
            )

        # Draw on-screen cards for characters and equipment
        if self.paused and not mouse_on_button:

            if self.box.collidepoint(b.MouseV.instance.v):
                displayed = False
                for character in self.characters:

                    if displayed:
                        break

                    for equipment in character.drawn_equipment:
                        if character.drawn_equipment[equipment].collidepoint(b.MouseV.instance.custom_pointer):
                            draw_groups['box'].append(equipment.loot_cards[None].draw(position=b.MouseV.instance.v))
                            displayed = True
                            break

                    if displayed:
                        break

                    # If no equipment overlaps, try to display statcard instead:
                    for rect in character.hitbox:
                        if rect.collidepoint(b.MouseV.instance.custom_pointer):
                            draw_groups['box'].append(character.stat_cards[None].draw(position=b.MouseV.instance.v))
                            displayed = True
                            break

        # In both pause and loot overlay, if mouse is hovering over inventory rects, show loot cards
        if self.player and self.player.inventory and (
                any((self.paused, self.loot_overlay)) and
                self.player.inventory.rect.collidepoint(b.MouseV.instance.v)
        ):
            mouse_in_inv = v(b.MouseV.instance.v) - v(self.player.inventory.rect.left, self.player.inventory.rect.top)
            for slot in self.player.inventory.slot_rects:
                if self.player.inventory.slot_rects[slot].collidepoint(mouse_in_inv):
                    armament = self.player.slots[slot]
                    # Empty slots return nothing:
                    if not armament:
                        break

                    # If slot is backpack, find which weapon should it compare to:
                    if slot == 'backpack':
                        compare_slot = armament.prefer_slot
                        compare_armament = self.player.slots[compare_slot] if self.player.slots[compare_slot] else None

                    # If slot is anything else, test if it's comparable to backpack:
                    else:
                        if not self.player.slots['backpack'] or self.player.slots['backpack'].prefer_slot != slot:
                            compare_armament = None
                        else:
                            compare_armament = self.player.slots['backpack']

                    if compare_armament not in armament.loot_cards:
                        armament.loot_cards[compare_armament] = b.LootCard(armament, compare_to=compare_armament)

                    draw_groups['box'].append(armament.loot_cards[compare_armament].draw(
                        position=b.MouseV.instance.v,
                        draw_compared=True
                    ))

        # Draw held mouse if exists
        if self.held_mouse is not None:
            draw_groups['box'].append(self.held_mouse.draw(b.MouseV.instance.v))

        if self.draw_group_append:
            draw_groups['box'].extend(self.draw_group_append)
            self.draw_group_append = []

        # Draw on field surface:
        field = self.field.copy()

        # Only draw if it is in view:
        in_view: list = list()
        for surface, dest in draw_groups['field']:
            # dest_list = dest[:]
            # dest_list[:2] = v(dest_list[:2]) + SHAKER_BUFFER
            # dest = dest.__class__(*dest_list)
            if fov_rect.colliderect(surface.get_rect(topleft=dest) if isinstance(dest, v) else dest):
                in_view.append((surface, dest))

        field.blits(in_view, doreturn=False)

        # Add field to box contents:
        draw_groups['box'].insert(0, [field.subsurface(fov_rect), self.box])

        # Display hitboxes if Tab is toggled
        if self.display_debug:

            for character in self.characters:
                for hand in character.weapon_slots:
                    hitbox = character.slots[hand].hitbox()
                    if hitbox and hitbox[0] and hitbox[1]:
                        hilt = r(*hitbox[0], 10, 10)
                        tip = r(*hitbox[1], 10, 10)
                        pygame.draw.rect(field, (255, 0, 0), hilt)
                        pygame.draw.rect(field, (0, 255, 0), tip)

                for hitbox in character.hitbox:
                    pygame.draw.rect(field, (255, 255, 0), hitbox, width=2)

                if character.ai:
                    topleft = character.position + character.body_coordinates[character.ai.slot] - \
                              v(character.ai.stab_reach_rx, character.ai.stab_reach_ry)
                    reach_rect = r(topleft, (character.ai.stab_reach_rx * 2, character.ai.stab_reach_ry * 2))

                    if character.facing_right:
                        angle_range = -math.pi / 2, +math.pi / 2
                    else:
                        angle_range = +math.pi / 2, -math.pi / 2

                    pygame.draw.arc(
                        field,
                        (64, 0, 0),
                        reach_rect,
                        *angle_range,
                        width=2
                    )

                    strategy: s = ascii_draw(BASE_SIZE // 2, character.ai.strategy, c(255, 0, 0))
                    state: s = ascii_draw(BASE_SIZE // 2, character.state, c(255, 0, 0))
                    strategy_place = character.position.x, character.position.y - BASE_SIZE * 3
                    strategy_rect: r = strategy.get_rect(center=strategy_place)
                    state_place = character.position.x, character.position.y - BASE_SIZE * 4
                    state_rect: r = state.get_rect(center=state_place)
                    field.blit(strategy, strategy_rect)
                    field.blit(state, state_rect)

                # Draw aiming vector
                elif self.player is character:
                    pygame.draw.line(
                        field,
                        c(127, 127, 255),
                        self.player.position,
                        self.pointer
                    )

                global _fps_querried_time
                global _fps_count

                _fps_querried_time += CLOCK.get_time()
                if _fps_querried_time >= 1000:
                    _fps_count = ascii_draw(40, str(int(CLOCK.get_fps())), (255, 255, 0))
                    _fps_querried_time = 0
                field.blit(_fps_count, fov_rect)

                # Add timer:
                time_surf = ascii_draw(BASE_SIZE, f"{self.timer:.3f}", (127, 255, 127))
                draw_groups['box'].append((
                    time_surf,
                    time_surf.get_rect(topright=self.box.topright)
                ))

        # Draw box contents unconditionaly:
        try:
            pygame.display.update(self.window.blits(blit_sequence=draw_groups["box"], doreturn=1))
        except ValueError as error:
            print("Could not draw following:")
            [print(pair) for pair in draw_groups["box"]]
            raise ValueError(error)

        CLOCK.tick(FPS_TARGET)

    def collide(self):
        """
        Collide all weapons with all weapons and character hitboxes with other collision groups. Return set of contact
        pairs that must be processed.
        """
        # 0. List of weapons is extracted and ordered. It is stored in Scene.weapons.
        # 1. Each frame, the list is copied and iterated over
        collision_quintet = []  # Hitting weapon, target, target's owner
        already_hit = []  # Do not iterate over each weapon more than once

        def log_collision(weapon_1, weapon_owner, victim, victim_owner, contact_point):
            collision_quintet.append((weapon_1, weapon_owner, victim, victim_owner, contact_point))
            already_hit.extend([weapon_1, victim])

        # Player weapons are iterated over first
        if self.player in self.characters and self.player is not self.characters[0]:
            oldindex = self.characters.index(self.player)
            self.characters.insert(0, self.characters.pop(oldindex))

        # Log all collisions
        for character in filter(lambda x: not x.phasing, self.characters):
            # Check if disabled characters have a particle associated with them; if not, spawn one:
            if character.state in DISABLED and character.immune_timer <= 0:
                has_particle = any(filter(
                    lambda x: isinstance(x, pt.Stunned) and x.character is character,
                    self.particles
                ))
                if not has_particle:
                    self.particles.append(pt.Stunned(character))

            if character in set(already_hit) or character.ignores_collision():
                continue

            target_characters = [
                x for x in self.characters
                if x.collision_group != character.collision_group and x is not character and not x.ignores_collision()
            ]

            # Don't check weapons of disabled characters:
            if character.state not in DISABLED and character.anchor_weapon is None:
                for weapon in self.colliding_weapons[character]:
                    # Don't iterate over non-dangerous, disabled or deflected weapons:
                    if (
                            (not weapon.dangerous and abs(weapon.angular_speed) < SWING_THRESHOLD * 0.5) or
                            weapon.disabled or
                            not weapon.hitbox() or
                            weapon in set(already_hit) or
                            (isinstance(weapon, eq.Pointed) and weapon.kebab)
                    ):
                        continue
                    weapon_cleared = False

                    # We might need to calculate weapon tip trail to find collisions "between" frames
                    if weapon.tip_delta:
                        tip_trail = weapon.tip_v, weapon.tip_v - weapon.tip_delta
                    else:
                        tip_trail = None

                    # First, attempt to collide with all other weapons from different characters
                    for foe in target_characters:

                        if weapon_cleared:
                            continue

                        # Skewered by weapon characters are not colliding with it neither with body nor weapons:
                        if isinstance(weapon, eq.Pointed) and foe is weapon.kebab:
                            continue

                        for target_weapon in self.colliding_weapons[foe]:

                            # 1 Frame = 1 hit
                            if (
                                    target_weapon in set(already_hit) or
                                    target_weapon.disabled or
                                    not target_weapon.hitbox() or
                                    not weapon.can_parry or
                                    not target_weapon.can_parry or
                                    foe.state in DISABLED
                            ):
                                continue

                            # Before intersecting weapon hitboxes which are SEGMENTS, run a cheap test to see if
                            # drawn RECTS intersect:
                            try:
                                if not character.drawn_equipment[weapon].colliderect(
                                        foe.drawn_equipment[target_weapon]
                                ):
                                    continue
                            except KeyError:
                                # Ignore non-drawn weapons
                                continue

                            # If hitboxes intersect, extend output pairs and add both to already_hit
                            try:
                                if intersect_lines(weapon.hitbox(), target_weapon.hitbox()):
                                    collision_point = (weapon.hitbox()[0][0] + weapon.hitbox()[1][0]) // 2, \
                                                      (weapon.hitbox()[0][1] + weapon.hitbox()[1][1]) // 2
                                    weapon_cleared = True
                                    log_collision(weapon, character, target_weapon, foe, collision_point)
                                    break

                                # Intersect target weapon with tip trail
                                if tip_trail and intersect_lines(tip_trail, target_weapon.hitbox()):
                                    collision_point = (weapon.hitbox()[0][0] + weapon.hitbox()[1][0]) // 2, \
                                                      (weapon.hitbox()[0][1] + weapon.hitbox()[1][1]) // 2
                                    weapon_cleared = True
                                    log_collision(weapon, character, target_weapon, foe, collision_point)
                                    break
                            except TypeError:
                                # Sometimes hitbox may disappear for a frame after roll; this is normal
                                break

                        # If no weapon was hit, collide with foe hitboxes
                        # Ignore Players that were hit recently (or this frame)
                        if (
                                not weapon.dangerous or
                                foe.immune_timer > 0 or
                                foe in set(already_hit) or
                                foe.ignores_collision()
                        ):
                            continue

                        # Attempt to collide with each of foes hitboxes:
                        for rectangle in foe.hitbox:
                            # Test simple rectangle collision:
                            try:
                                if not character.drawn_equipment[weapon].colliderect(rectangle):
                                    continue
                            except KeyError:
                                # Ignore non-drawn weapons
                                continue

                            if rectangle.collidepoint(weapon.tip_v):
                                weapon_cleared = True
                                log_collision(weapon, character, foe, foe, weapon.tip_v)
                                break
                            try:
                                clipped_line = rectangle.clipline(tip_trail)
                                if clipped_line:
                                    weapon_cleared = True
                                    log_collision(weapon, character, foe, foe, clipped_line[0])
                                    break

                                # Swords and axes should also attempt to intersect with full hitbox length:
                                clipped_line = rectangle.clipline(weapon.hitbox())
                                if isinstance(weapon, eq.Bladed) and clipped_line:
                                    weapon_cleared = True
                                    log_collision(weapon, character, foe, foe, clipped_line[0])
                                    break
                            except TypeError:
                                # Sometimes hitbox may disappear for a frame after roll; this is normal
                                break

            # Also attempt to collide own body with ALL characters
            for rectangle in character.hitbox:
                # if we are already hit in this cycle or airborne
                if character in set(already_hit) or character.ignores_collision():
                    continue

                for meatbag in self.characters:
                    # Don't iterate over:
                    #  over self
                    #  over already hit characters
                    #  if we are already hit in this cycle
                    #  target is airborne
                    #  target is anchored to a weapon
                    #  meatbag is anchored to a weapon
                    if (
                            meatbag is character or
                            meatbag in set(already_hit) or
                            character in set(already_hit) or
                            character.ignores_collision() or
                            meatbag.ignores_collision() or
                            (character.anchor_timer > 0 and character.anchor_weapon is not None) or
                            (meatbag.anchor_timer > 0 and meatbag.anchor_weapon is not None)
                    ):
                        continue

                    collision_index = rectangle.collidelist(meatbag.hitbox)
                    if collision_index != -1:
                        log_collision(character, character, meatbag, meatbag, character.position)

        # Now process collsions:
        for weapon, owner, target, opponent, point in collision_quintet:

            # Process weapon hits
            if isinstance(weapon, eq.Wielded):
                if isinstance(target, b.Character):
                    collision_v = target.speed + weapon.tip_delta
                    damage = weapon.deal_damage(vector=collision_v, victim=target, victor=owner)
                    survived, actual_damage = opponent.hurt(
                        damage=round(damage[0]),
                        vector=weapon.tip_delta,
                        weapon=weapon,
                        offender=owner
                    )

                    # Shield effects:
                    if isinstance(target.shielded, eq.Shield) and actual_damage == 0:
                        shield = target.shielded

                        # If player was hit or performed the hit, add small screenshake:
                        if self.player is target:
                            # Wielding lighter shield causes heavier screenshake:
                            self.shaker.add_shake(0.001 * damage[0] * (10 - shield.weight))
                            play_sound('shield', 0.01 * damage[0])
                        elif self.player is owner:
                            self.shaker.add_shake(0.0025 * damage[0])
                            play_sound('shield', 0.005 * damage[0])

                    # If actual damage is below zero, apply it back to attacker (For Buckler?)
                    elif actual_damage < 0:
                        opponent_survived, opponent_actual_damage = owner.hurt(
                            damage=-actual_damage,
                            vector=-weapon.tip_delta,
                            weapon=target.shielded,
                            offender=target,
                            deflectable=False
                        )
                        if not opponent_survived:
                            self.undertake(owner)
                        elif opponent_actual_damage > 0:
                            play_sound('hurt', opponent_actual_damage * 0.01)
                            self.alert_ai(owner)

                        self.splatter(weapon.hilt_v, owner, opponent_actual_damage, opponent.shielded)

                    elif not survived:
                        self.undertake(target)
                    # Cause FOF reaction in bots
                    elif actual_damage > 0:
                        play_sound('hurt', actual_damage * 0.01)
                        self.alert_ai(target)

                    # Spawn kicker and blood:
                    self.splatter(point, target, actual_damage, weapon, crit=damage[1])

                    # Half shakeup for crits and Executions, quarter for everything else
                    if owner is self.player:
                        if actual_damage == weapon.damage_range[1] or target.anchor_weapon is not None:
                            self.shaker.add_shake(0.005 * actual_damage)
                        else:
                            self.shaker.add_shake(0.0025 * actual_damage)

                elif isinstance(target, eq.Wielded):
                    # If player is participating and both weapons are dangerous, shake the scene:
                    if (
                            OPTIONS["screenshake"] and
                            self.player in {owner, opponent} and
                            weapon.dangerous and
                            target.dangerous
                    ):
                        enemy_weapon = target if self.player is owner else weapon
                        # Calculate the impact force
                        speed_impact = (weapon.tip_delta - target.tip_delta).length_squared() / \
                                       (9 * POKE_THRESHOLD * POKE_THRESHOLD)
                        # Calculate weight of enemy weapon:
                        weight_impact = enemy_weapon.weight / 18
                        self.shaker.add_shake(speed_impact * weight_impact)

                    # Perform parry
                    weapon.parry(owner, opponent, target)

                    # Spawn sparks
                    for hitting_weapon in {weapon, target}:
                        for _ in range(random.randint(2, 3)):
                            spark = pt.Spark(
                                position=point,
                                weapon=hitting_weapon,
                                vector=hitting_weapon.tip_delta / 2,
                                attack_color=hitting_weapon.color
                            )
                            self.particles.append(spark)
                else:
                    raise ValueError(f"What are we hitting again? {target}")

            # Process body checks
            elif isinstance(weapon, b.Character) and isinstance(target, b.Character):
                # Reorder colliding agents if target is ramming:
                if target.ramming:
                    weapon, owner, target, opponent = target, opponent, weapon, owner

                collision_v = weapon.position - target.position

                # Shield hits processed here
                if weapon.collision_group != target.collision_group and weapon.ramming and not target.immune_timer > 0:
                    shield = weapon.slots["off_hand"]

                    # Calculate collision vector
                    collision_v = v(weapon.speed) * shield.weight * 0.1 * (1-target.knockback_resistance)

                    # Shield damage is static, push target for remaining charge duration + 0.5 s
                    shield_damage = shield.deal_damage(v())
                    survived, bash_damage = target.hurt(
                        damage=shield_damage[0],
                        vector=collision_v,
                        offender=weapon,
                        duration=min(1.5, 0.5 + weapon.state_timer),
                        deflectable=False  # Shield bash can't be blocked
                    )

                    play_sound('shield', 1)

                    if not survived:
                        self.undertake(target)
                    # Cause FOF reaction in bots
                    else:
                        self.alert_ai(target)

                    self.splatter(target.position, target, bash_damage, shield, crit=shield_damage[1])
                    self.shaker.add_shake(1.0)

                    for _ in range(random.randint(5, 7)):
                        spark = pt.Spark(
                            position=point,
                            weapon=shield,
                            vector=v(weapon.speed[:]),
                            attack_color=shield.color,
                            angle_spread=(-45, 45)
                        )
                        self.particles.append(spark)

                    # Stop the bashing character and portion of missing stamina:
                    if bash_damage > 0:
                        # Light (agile) shields restore more
                        weapon.stamina += (weapon.max_stamina - weapon.stamina) * shield.agility_modifier
                        weapon.anchor(min(weapon.state_timer, 0.5))
                        weapon.set_state('active', 0.2)

                # Process flying disabled characters hitting teammates
                elif (
                        (target.is_flying_meat() or weapon.is_flying_meat()) and
                        target.collision_group == weapon.collision_group and
                        (target.immune_timer <= 0 or weapon.immune_timer <= 0)
                ):
                    # Test if collision speed above PT/2
                    relative_v = weapon.speed - target.speed
                    if 4 * relative_v.length_squared() < POKE_THRESHOLD * POKE_THRESHOLD:
                        # Simple collision
                        collision_v.scale_to_length(POKE_THRESHOLD)
                        if not (weapon.shielded or weapon.anchor_timer > 0):
                            weapon.push(collision_v, 0.2, 'active')
                        if not (target.shielded or weapon.anchor_timer > 0):
                            target.push(-collision_v, 0.2, 'active')

                    else:
                        # Pinball time! Damage the vulnearable or non-skewerd one or slower one
                        assigned = [weapon, target]
                        assigned.sort(key=lambda x: (x.immune_timer, x.state == 'skewered', x.speed.length_squared()))
                        target, weapon = assigned

                        damage_modifier = lerp(
                            (0.25 * POKE_THRESHOLD * POKE_THRESHOLD, 2.25 * POKE_THRESHOLD * POKE_THRESHOLD),
                            relative_v.length_squared())
                        impact_damage = 0.05 * weapon.knockback_resistance * damage_modifier
                        play_sound('collision', 0.01 * impact_damage)

                        # Cap impact damage at 15% of target health:
                        impact_damage = min(impact_damage, target.pct_cap * target.max_hp)

                        survived, damage = target.hurt(
                            damage=impact_damage,
                            vector=weapon.speed,
                            offender=weapon,
                            deflectable=False  # Can't be blocked
                        )

                        if not survived:
                            self.undertake(target)
                        # Cause FOF reaction in bots
                        else:
                            self.alert_ai(target)

                        self.splatter(
                            point=v(target.position[:]),
                            target=target,
                            damage=impact_damage
                        )

                        # Slow down hitting character
                        weapon.speed *= 0.5 * weapon.knockback_resistance / target.knockback_resistance

                else:
                    # Play sound (but not too often)
                    if self.player in (weapon, target):
                        stamp = pygame.time.get_ticks()
                        if stamp - self.player.last_bump > 1000:
                            self.player.last_bump = stamp
                            play_sound('collision', 0.2)
                    collision_v.scale_to_length(POKE_THRESHOLD)
                    if not (weapon.shielded or weapon.anchor_timer > 0):
                        weapon.push(collision_v, 0.2, 'active')
                    if not (target.shielded or weapon.anchor_timer > 0):
                        target.push(-collision_v, 0.2, 'active')

            else:
                raise ValueError(str(weapon) + " is not a valid collision agent")

        # Process weapon particles and destroyed equipment:
        for character in self.characters:
            for slot in character.slots:
                equipment = character.slots[slot]

                # Querry character equipment to collect particles
                self.particles.extend(equipment.particles)
                equipment.particles = []

                if equipment.queue_destroy:
                    # Destroying a shields cause screenshake
                    self.shaker.add_shake(equipment.weight * 0.125)
                    self.item_drop(character, equipment, slot)
                    # Inform AI it no longer has a shield
                    character.shielded = None
                    self.log_weapons()

        # Process characters hitting walls:
        for character in filter(
                lambda x: x.wall_collision_v != v() and character.hp > 0,
                self.characters
        ):

            if (
                    character.wall_collision_v.length_squared() < 0.25 * POKE_THRESHOLD * POKE_THRESHOLD or
                    (character.ai is None and character.immune_timer > 0) or
                    not character.drops_shields
            ):
                character.wall_collision_v = v()
                continue

            damage_modifier = lerp((0.25 * POKE_THRESHOLD * POKE_THRESHOLD, 9 * POKE_THRESHOLD * POKE_THRESHOLD),
                                   character.wall_collision_v.length_squared())
            impact_damage = 0.025 * character.weight * damage_modifier
            play_sound('collision', 0.01 * impact_damage)

            # Cap at 15% max_hp
            impact_damage = min(impact_damage, character.pct_cap * character.max_hp)

            survived, damage = character.hurt(
                damage=impact_damage,
                vector=v(),
                deflectable=False  # Can't be blocked
            )

            if not survived:
                self.undertake(character)
            # Cause FOF reaction in bots
            else:
                self.alert_ai(character)

            self.splatter(
                point=v(character.position[:]),
                target=character,
                damage=impact_damage
            )
            self.shaker.add_shake(character.size / 2 * BASE_SIZE)
            character.wall_collision_v = v()

    def splatter(self, point, target, damage, weapon=None, crit=False):
        if damage <= 0:
            return

        # Modify combo counter, if it's here:
        if self.combo_counter:
            if target is self.player:
                self.combo_counter.reset()
            else:
                self.player_damage += damage
                self.combo_counter.increment()
                self.max_combo = max(self.combo_counter.counter, self.max_combo)

        # Spawn kicker
        kicker = pt.Kicker(
            point,
            damage,
            color=colors["dmg_kicker"],
            weapon=weapon,
            critcolor=colors["crit_kicker"],
            draw_crit=crit
        )
        self.particles.append(kicker)

        if target.has_blood and not OPTIONS["red_blood"] == 2:
            # Spawn a blood particle 50% of the time for each 7 damage suffered
            # Spawn 1 instantly always:
            first_blood = pt.Droplet(point, target, spawn_delay=0)
            self.particles.append(first_blood)

            for _ in range(int(damage // 7)):
                if random.random() > 0.5:
                    continue

                blood = pt.Droplet(point, target)
                self.particles.append(blood)
        else:
            # Spawn pt.Sparks of body color
            for _ in range(int(damage // 7)):
                if random.random() > 0.5:
                    continue

                if weapon:
                    vector = weapon.tip_delta * -4
                else:
                    vector = v()
                    vector.from_polar((
                        random.triangular(0, 3 * POKE_THRESHOLD),
                        random.uniform(-180, 180)
                    ))
                blood = pt.Spark(target.position, vector, attack_color=target.color, angle_spread=(-60, 60))
                self.particles.append(blood)

        if target is self.player:
            self.shaker.add_shake(damage * 0.01)

    def undertake(self, character):
        play_sound('death', character.size / BASE_SIZE)
        character.hp = -1

        friends_alive = any(filter(
            lambda x: x.collision_group == character.collision_group and x is not character,
            self.characters
        )
        )

        if not friends_alive:
            for enemy in filter(lambda x: x.collision_group != character.collision_group, self.characters):
                enemy.set_state('pog', 2)

        try:
            self.characters.remove(character)
            self.dead_characters.append(character)
        except ValueError:
            # Something already killed it
            pass

        # Log count of enemies if it's enemy who died:
        if character.collision_group != 0:
            self.enemies_count_on_death.append(self.count_enemies_value())

        self.particles.append(pt.Remains(
            *character.kill(),
            bounding_box=self.field_rect,
            particle_dump=self.particles
        ))
        self.log_weapons()
        self.alert_ai(character)

        # If target was a Boss, remove hp bar and stop music:
        if isinstance(character, bs.Boss):
            # Make sure loot sounds do not override each other:
            if not character.loot:
                play_sound('loot', 1)
            self.boss_bar = None
            self.boss_name.tick_down = True
            end_theme()

        # If target was Player, increment player death count:
        elif character is self.player:
            self.player_deaths += 1

    def iterate(self):
        # Unless scene is paused, increase timer:
        if not (self.paused or self.menus):
            self.timer += FPS_TICK

        # May happen when scene is handed over:
        # if player is specified, and not in dead characters, make sure it is in characters list
        if self.player and self.player not in self.dead_characters and self.player not in self.characters:
            self.characters = [self.player] + self.characters
            self.log_weapons()

        # Calculate shake vector
        if OPTIONS["screenshake"]:
            self.shake_v = self.shaker.get_current_v()
        else:
            self.shaker.reset()
            self.shake_v = v()

        # Iterate scene:
        self.update_input()
        self.draw()

        # Collide only once each 2 frames:
        if self.collide_this_frame and not (self.paused or self.loot_overlay):
            self.collide()
        self.collide_this_frame = not self.collide_this_frame

        # Prevent losing mouse:
        pygame.event.set_grab(OPTIONS["grab_mouse"] and not self.paused and not self.menus)

        # Pause game and music on losing focus:
        if unfocused():
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()

            if not (self.paused or self.loot_overlay):
                self.toggle_pause()

            # Kill sounds:
            if pygame.mixer.get_busy():
                pygame.mixer.stop()

        else:
            # Unpause music:
            if OPTIONS["music"] and hd.SceneHandler.active.theme and not pygame.mixer.music.get_busy():
                pygame.mixer.music.unpause()

    def spawn(self, monster, position_v=None):

        # Find box in which to spawn enemy, close to the player:
        if self.player:
            box = self.box.copy()
            box.center = self.player.position[:]
            box.clamp_ip(self.field_rect)
        else:
            box = self.field_rect

        # If monster is bs.Boss with a music theme, play its theme:
        if OPTIONS["music"] and isinstance(monster, bs.Boss) and monster.theme is not None:
            play_theme(os.path.join('music', monster.theme))

        # If monster is bs.Boss, spawn an HP bar
        if isinstance(monster, bs.Boss):
            self._add_boss_bar(monster)

        # High agility and flexibility monsters may roll in instead of jumping
        roll_in = monster.agility > 1.2 and random.random() < max(monster.ai.flexibility, 0.5)

        def roll_position(left=False):
            # Offset from center
            x_offset = random.uniform(box.width // 3, box.width // 4)
            if left:
                x_offset *= -1

            position = v(
                box.left + box.width // 2 + + x_offset,
                box.top + random.randint(box.height // 4, box.height * 3 // 4)
            )

            return position

        # Spawn away from the player, or at random if player is absent
        if self.player is not None:
            spawn_left = self.player and self.player.position.x > self.field_rect.left + self.field_rect.width * 0.5
        else:
            spawn_left = random.random() > 0.5

        if spawn_left != monster.facing_right:
            monster.flip(dormant=True)

        if position_v is None:
            # Pick a random position in bounding box: horizontally between 2/3 and 5/6, vertically between 1/4 and 3/4
            position_v = roll_position(left=spawn_left)

        # If there is a character near target position, reroll position_v
        clear = not any((meatbag.position - position_v).length_squared() < 9 * BASE_SIZE for meatbag in self.characters)
        while not clear:
            position_v = roll_position(left=spawn_left)
            clear = not any((meatbag.position - position_v).length_squared() < BASE_SIZE * POKE_THRESHOLD
                            for meatbag in self.characters)

        off_screen_x = random.uniform(3, 6) * monster.size

        if roll_in:
            # Calculate rolling in from distance

            # Add slight vertical offset
            off_screen_y = random.uniform(-BASE_SIZE, BASE_SIZE)

            # Calculate starting roll position
            roll_from_v = v()
            roll_from_v.x = box.left - off_screen_x if spawn_left else box.right + off_screen_x
            roll_from_v.y = position_v.y + off_screen_y

            # Calculate roll vector
            roll_v = FPS_TICK * (position_v - roll_from_v)

            # Execute roll
            position_v = roll_from_v
            monster.roll(roll_v)

        else:
            # Calculate a parabollic jump from outside the screen to land monster in the required position
            jump_time = random.uniform(1.5, 2)
            if spawn_left:
                jump_x = position_v.x - box.left + off_screen_x
            else:
                jump_x = position_v.x - box.right - off_screen_x

            position_v.x -= jump_x

            # Calculate initial movement vector
            jumping_v = v(
                jump_x * FPS_TICK / jump_time,
                -0.5 * jump_time * FFA.y * FPS_TARGET
            )
            monster.push(jumping_v, jump_time, 'jumping')

        monster.position = position_v
        self.characters.append(monster)
        self.log_weapons()
        monster.ai.analyze(self, initial=True)

    def respawn(self, character, position):
        if character not in self.dead_characters:
            raise KeyError("Can't find this name in my graveyard")

        character.reset()
        character.position = position

        if character.ai:
            character.ai.analyze(self, initial=True)
        elif not character.facing_right:
            # Make sure we spawn players facing right
            character.flip()

        self.dead_characters.remove(character)

        # Put players first in the list
        if not character.ai:
            self.characters.insert(0, character)
        else:
            self.characters.append(character)
        self.log_weapons()

    def toggle_pause(self):
        # Background scene can not be paused:
        if self.decorative:
            self.hard_unpause()

        # Only if player exists
        if not self.player:
            return

        if not self.paused:
            # Pause instantly
            self.pause_popups = mn.PauseEnsemble(self)
            self.paused = True

            # Update stat cards for every character
            for character in self.characters:
                for compare_key in character.stat_cards:
                    character.stat_cards[compare_key].redraw()

            # Reduce theme music volume:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.set_volume(0.2*OPTIONS["music"]/4)

        # Spawn countdown to unpause, unless it is already in scene particles:
        elif OPTIONS["unpause_countdown"] != 0 and not any(
                True
                for countdown in self.particles
                if isinstance(countdown, pt.CountDown) and countdown.action == self.hard_unpause
        ):
            self.pause_popups.fade()
            self.particles.append(pt.CountDown(
                self.hard_unpause,
                {},
                colors["pause_popup"],
                position=self.box.center[:],
                go_text="GO!" if OPTIONS["unpause_countdown"] == 2 else None,
                ignore_pause=True,
                total_duration=OPTIONS["unpause_countdown"]
            ))

        else:
            self.hard_unpause()

    def count_enemies_value(self):
        if self.player is None:
            return 0

        return sum(
            enemy.difficulty
            for enemy
            in filter(
                lambda x: x.collision_group != self.player.collision_group,
                self.characters
            )
        )

    def item_drop(self, character, dropped_item, slot=None, equip=True):
        # Animate remains
        if dropped_item:
            self.particles.append(pt.Remains(
                [dropped_item.drop(character)],
                persistence=1,
                bounding_box=self.box,
                particle_dump=self.particles
            ))

        # Equip nothing in slot if it was occupied:
        if equip:
            character.equip(b.Nothing(), slot or dropped_item.preferred_slot)

        self.log_weapons()

    def echo(self, character, text, color):
        character.set_state('talk', 2)
        x_position = character.position.x + self.conversion_v.x
        offset = v(4 * BASE_SIZE if x_position < self.box.center[0] else -4 * BASE_SIZE, -3 * BASE_SIZE)

        self.particles.append(
            pt.SpeechBubble(
                offset,
                c(color),
                character,
                text,
                self.field_rect
            )
        )

    def hard_unpause(self):
        # Restore theme music volume:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.set_volume(MUSIC_VOLUME*OPTIONS["music"]/4)
        self.paused = False
        self.pause_popups = None

    def generate_menu_popup(self, menu_class, keywords=None):
        if keywords is None:
            keywords = dict()
        self.menus.append(menu_class(**keywords))

    def request_new_handler(self, scene_handler, args=None, kwargs=None):
        args = args or []
        kwargs = kwargs or dict()
        self.new_sh_hook = scene_handler(*args, **kwargs)

    def explosion(self, epicenter, max_distance, max_push=2, collision_group=None):
        play_sound('respawn', 1)
        base_pushback = POKE_THRESHOLD * max_push
        self.shaker.add_shake(1)

        # Push enemies away:
        for enemy in filter(lambda x: x.collision_group != collision_group, self.characters):
            if not enemy.position:
                continue

            direction = v(enemy.position) - v(epicenter) or v(-1, 0)

            # Don't affect enemies too far away
            if direction.length_squared() > max_distance * max_distance:
                continue

            # Modify pushback according to distance to explosion position (squared)
            direction.scale_to_length(base_pushback * (1 - direction.length_squared() / (max_distance * max_distance)))
            enemy.push(direction, 1.2)

        # Spawn sparks:
        for _ in range(random.randint(7, 12)):
            spark_v = v()
            spark_v.from_polar((3 * base_pushback, random.uniform(-180, 180)))
            spark = pt.Spark(
                position=epicenter[:],
                weapon=None,
                vector=spark_v,
                attack_color=colors["lightning"]
            )
            self.particles.append(spark)

    def monster_summon(self, summoner: b.Character, monsters: list):

        for monster in monsters:
            # Set minions difficulty to 0
            monster.difficulty = 0
            monster.collision_group = summoner.collision_group

            self.spawn(monster)

    def _add_boss_bar(self, boss: bs.Boss, font_size=BASE_SIZE, offset=BASE_SIZE // 2):
        # Calculate character size:
        test_surface = ascii_draw(font_size, '█', (255, 255, 255))

        # Calculate available rect, place it on top of the scene:
        boss_bar_rect = r(
            self.box.width // 3,
            offset * 2 + BASE_SIZE,
            self.box.width // 3,
            test_surface.get_height()
        ).move(*self.box.topleft)

        self.boss_bar = b.Bar(
            size=font_size,
            width=boss_bar_rect.width // test_surface.get_width(),
            fill_color=c(*colors['enemy']['hp_color'], 100),
            max_value=boss.max_hp,
            show_number=True,
            style="{– }"
        )

        # Add pt.Banner with bs.Boss name:
        self.boss_name = pt.Banner(
            text=boss.name.upper(),
            size=font_size * 3 // 2,
            position=v(self.box.width // 2, self.box.top + offset + font_size // 2),
            color=c(*colors['enemy']['hp_color'], 100),
            lifetime=3,
            animation_duration=1.5,
            tick_down=False
        )

        # Save bar center:
        self.boss_bar_center = v(boss_bar_rect.center)

    def report(self, report, color):
        # Spawn report banner
        report_position = WINDOW_SIZE[0] // 2, self.box.bottom - BASE_SIZE
        report_banner = pt.Banner(
            report,
            BASE_SIZE,
            report_position,
            color,
            lifetime=7,
            animation_duration=3.5,
            animation='slide',
            max_width=WINDOW_SIZE[0] * 2
        )
        self.particles.append(report_banner)


# Supplemental scene UI elements
class LootOverlay:
    def __init__(
            self,
            loot_list: list,
            character: b.Character,
            rect: r = LOOT_SPACE,
            label_size: int = BASE_SIZE * 3 // 2,
            label: str = 'LOOT TIME!',
            offset: int = BASE_SIZE,
            appear_from: v = None,
            animation_time: float = 1.5,
            draw_shortcuts=True,
            sound=True,
            banner=True
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
        self.helper = pt.LootOverlayHelp()

        # Play sound:
        if sound:
            play_sound('loot', 1)

        # Remember if banner is needed:
        self.banner = banner

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
                    loot.loot_cards[compare_to] = b.LootCard(loot, compare_to)
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
                shortcurt_surface = ascii_draw(BASE_SIZE * 2 // 3, NUMBER_LABELS[card_index], colors["inventory_title"])
                shortcut_rect = shortcurt_surface.get_rect(
                    topleft=v(loot_card_rect.topleft) + v(0.5 * self.offset, 0.5 * self.offset)
                )
                self.surface.blit(shortcurt_surface, shortcut_rect)

            # Offset loot_card_rect by parent surface topleft, to let clicks through
            loot_card_rect.move_ip(self.rect.left, self.rect.top)
            self.loot_dict[loot] = loot_card_rect
            x_offset += x_offset_iteration + loot_card_rect.width

            card_index += 1

    def draw(self):
        surface = self.surface.copy()

        # If no appearance point is set, no animation is required
        if self.appear_from is None or self.lifetime >= self.animation_time:
            return surface, self.rect

        # Else, find new position and scaled size
        progress = self.lifetime / self.animation_time
        self.lifetime += FPS_TICK

        # Position:
        start_v = self.appear_from
        end_v = v(self.rect.center)
        current_v = v(start_v.x * (1 - progress) + end_v.x * progress, start_v.y * (1 - progress) + end_v.y * progress)

        # Size:
        current_size = int(self.rect.width * progress), int(self.rect.height * progress)

        surface = pygame.transform.smoothscale(surface, current_size)
        rect = surface.get_rect(center=current_v)

        return surface, rect

    def catch(self, position, mouse_state):
        # If animation is not finished, instantly complete it, and return no click
        if any(mouse_state) and self.lifetime < self.animation_time:
            self.lifetime = self.animation_time

            # Return only if we had animation in the first place:
            if self.appear_from is not None:
                return None, None

        if not any(mouse_state):
            # Return loot, None slot
            for loot in self.loot_dict:
                if self.loot_dict[loot].collidepoint(position):
                    return loot, None

        for loot in self.loot_dict:
            if self.loot_dict[loot].collidepoint(position):
                if mouse_state[0]:
                    play_sound('button', 1)
                    return loot, loot.prefer_slot
                elif mouse_state[2]:
                    play_sound('button', 1)
                    return loot, 'backpack'

        return None, None

    def catch_index(self, index):
        # If animation is not finished, instantly complete it, and return no click
        if self.lifetime < self.animation_time:
            self.lifetime = self.animation_time
            # Return only if we had animation in the first place:
            if self.appear_from is not None:
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
            content: dict,
            base_color=DISPLAY_COLOR,
            rect=LEVEL_BAR_SPACE,
            font_size=BASE_SIZE * 2 // 3,
            offset=BASE_SIZE // 3
    ):
        # Initiate a surface:
        self.surface = s(rect.size, pygame.SRCALPHA)
        self.rect = rect
        self.base_color = c(base_color)
        self.font_size = font_size
        self.offset = offset

        # Contents (Bars and Indicators)
        self.content = content

        # Initiate:
        default_values = [(0 if isinstance(element, b.Bar) else False) for element in self.content]
        self.update(default_values)

    def update(self, values: list):
        self.surface.fill(self.base_color)
        # Draw from top and right:
        x, y = self.rect.width - self.offset, self.offset

        for i, (name, graphic) in enumerate(self.content.items()):
            value = values[i]

            if isinstance(graphic, b.Bar):
                surface, rect = graphic.display(value)
                rect.right, rect.top = x, y
                self.surface.blit(surface, rect)
                name_x = x - rect.width

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
                raise TypeError(f"Can't handle contents in progress bar:{graphic}")

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
            text_surface.get_width() // 2 - size,
            text_surface.get_height() // 2 + size,
            size * 2,
            size * 2
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
            start_angle=math.pi * (-0.5 + (2 * self.held_timer / self.max_timer)),
            stop_angle=-math.pi / 2,
            width=self.size // 4
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
