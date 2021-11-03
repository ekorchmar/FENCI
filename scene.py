# todo:
#  display combo counter
#  support for tiled arbitrary sized arenas
#  tile generation
# After tech demo
# todo:
#  scenario feeds dict with debug info into scene for display_debug
#  Player.fate: dict to remember player choices for future scenario, also displayed in stat card
#  cut off all surfaces by bounding box
#  separate skirmish scene handler
# todo: Add lightning effect to character spawn
# todo: draw complex background
#  sparks in inventory when weapon is damaged
#  character portrait, stats and name in topleft
#  Dialogues

from particle import *
from artifact import *
from monster import *

# Display FPS counters(initial state):
fps_querried_time = 1000
fps_count = ascii_draw(40, '0', (255, 255, 0))


# Scene class, that draws everything and processess game physics
class Scene:
    """Takes Rect as bounding box, list of enemies and a player"""

    def __init__(self, player, window, bounds, enemies=None, progression=None, decorative=False):
        self.window = window
        self.box = bounds
        self.decorative = decorative

        # Spawn player:
        self.player = player

        # Put player in characters list
        self.characters = []
        if self.player:
            self.characters.append(self.player)
        if enemies:
            self.characters.extend(enemies)

        self.character_states = {char: char.state for char in self.characters}

        self.collision_groups = set([char.collision_group for char in self.characters])
        # Order collision groups so that player is processed first:
        self.collision_groups = list(self.collision_groups)
        self.collision_groups.sort()

        # Updated with player input
        self.mouse_state = False, False, False
        self.last_mouse_state = False, False, False
        self.display_debug = False
        self.paused = False
        self.mouse_target = [0, 0]
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

        # Store display for level progress:
        self.progression = progression

        # Reserved for pause popups and banners:
        self.pause_popups = None
        self.loot_overlay = None
        self.draw_helper = False
        self.draw_group_append = []

        # Support drawing buttons and menus:
        self.menus = []

        # Property as shortcut for SceneHandler to know when to hand over; scene can not do it by itself
        self.new_sh_hook = None

        # Create own shaker for camera shake:
        self.shaker = Shaker()
        self.shake_v = v()

    def log_weapons(self):
        for character in self.characters:
            self.colliding_weapons[character] = []
            for slot in character.weapon_slots:
                weapon = character.slots[slot]
                if weapon.hitbox():
                    self.colliding_weapons[character].append(weapon)

        if self.player and self.player.inventory:
            self.player.inventory.update()

    def alert_ai(self, victim):
        for character in filter(lambda x: x.ai is not None, self.characters):
            # React to death:
            if victim in self.dead_characters:
                # Rigid AI gains less morale, Cowardly AI loses more
                character.ai.morale += 0.4 * character.ai.flexibility \
                    if victim.collision_group != character.collision_group \
                    else -0.2 - 0.1 * character.ai.courage

                # Respect boundaries
                character.ai.morale = min(character.ai.morale, 1.0)
                character.ai.morale = max(character.ai.morale, 0.0)

            character.ai.fight_or_flight(victim)

    def update_input(self):

        spacebar, debug, wheel, escape = False, False, False, False
        number_keys = [False]*9

        for event in pygame.event.get():  # User did something

            if event.type == pygame.QUIT:  # If user closed the window
                exit_game()

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

        self.mouse_target = v(pygame.mouse.get_pos())
        self.mouse_state = pygame.mouse.get_pressed(num_buttons=3)
        keyboard = pygame.key.get_pressed()

        # Digest held buttons input:
        movement = keyboard[pygame.K_w], keyboard[pygame.K_a], keyboard[pygame.K_s], keyboard[pygame.K_d]
        shift = keyboard[pygame.K_LSHIFT]

        self.draw_helper = False

        # Debug:
        if debug:
            if self.player and self.player in self.characters:
                self.echo(self.player, "Let's make some noise!", colors["lightning"])

            for character in self.characters:
                if character.ai is not None and 'ccw' in character.ai.strategy_dict:
                    self.echo(character, 'ccw' if character.ai.strategy_dict["ccw"] else 'cw', colors["lightning"])
            # play_sound(random.choice(list(SOUND.keys())), 1.0)
            play_sound('landing', 1)
            # print("No debug action set at the moment.")
            # morph_equipment(self.player)
            # random_frenzy(self, 'charge')
            # self.player.equip_basic()
            # self.log_weapons()
            # self.menus.append(Defeat(self))
            # self.shaker.add_shake(1.0)

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
                if char == self.player:
                    # Move:
                    char_direction = kb_move(movement)
                    speed_limit = 1.0

                    # Use:
                    for i in range(3):
                        if self.mouse_state[i]:
                            continuous = self.last_mouse_state[i]
                            self.player.use(PLAYER_SLOTS[i], continuous)

                    # Aim:
                    if not shift:
                        aiming = self.mouse_target
                    else:
                        aiming = None
                # Listen to AI choices:
                else:
                    char_direction, aiming = char.ai.execute()
                    speed_limit = char.ai.speed_limit

                char.aim(aiming)
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
                        for _ in range(int(char.weight*0.02)):
                            self.particles.append(DustCloud(random.choice(char.hitbox)))
                except KeyError:
                    continue
            self.character_states = new_character_states

            # Spawn blood particles for continiously bleeding characters
            for bleeding_character in filter(lambda x: x.bleeding_timer > 0, self.characters):
                # On average, 10 droplets per second
                if isinstance(bleeding_character, Character) and random.random() < 10*FPS_TICK:
                    droplet = Droplet(
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
        elif self.loot_overlay:
            if self.loot_overlay.rect.collidepoint(self.mouse_target):

                # Middle click closes overlay
                if self.mouse_state[1]:
                    self._close_and_repair()

                else:
                    # Draw help around the mouse:
                    self.draw_helper = True

                    # Pass mouse click to loot overlay:
                    result = self.loot_overlay.catch(self.mouse_target, self.mouse_state)
                    # Prevent accidental mouse holds
                    if all(result) and self.mouse_state != self.last_mouse_state:
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
                                ascii_draw(BASE_SIZE*2//3, string["equipped"], colors["inventory_title"]),
                                (self.loot_overlay.offset*0.5, self.loot_overlay.offset*0.5)
                            )
                            self.draw_group_append.append([card_surface, card_rect])

                # Fully heal player no matter the picked option:
                self.player.hp, self.player.stamina = self.player.max_hp, self.player.max_stamina

            if any(number_keys):
                result = self.loot_overlay.catch_index(number_keys.index(True))
                self._from_loot_overlay(*result)

        # Allow to drop weapons in pause or loot overlay:
        if (
                self.player and
                (self.loot_overlay or self.paused) and
                self.player.inventory.rect.collidepoint(self.mouse_target)
        ):

            # Can't drop last damaging weapon:
            not_last_weapon = len(list(filter(
                lambda x: self.player.slots[x],
                self.player.weapon_slots + ['backpack']
            ))) > 1

            if not_last_weapon and self.held_mouse is None and self.mouse_state[0]:

                # Spawn a held_mouse object that will drop from inventory
                for slot in self.player.inventory.slot_rects:

                    modified_target = v(self.mouse_target) - v(
                        self.player.inventory.rect.left,
                        self.player.inventory.rect.top
                    )

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
            if not self.mouse_state[0] or self.held_mouse.hold():
                self.held_mouse = None

        # Handle most recent displayed menu:
        if self.menus:
            # Set cursor shape:
            pygame.mouse.set_system_cursor(pygame.SYSTEM_CURSOR_ARROW)

            if self.mouse_state[0] and not self.last_mouse_state[0]:
                self.menus[-1].collide_button(self.mouse_target)

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

            if self.mouse_state[0] and not self.last_mouse_state[0]:
                self.pause_popups.collide_button(self.mouse_target)

            elif any(number_keys):
                self.pause_popups.index_button(number_keys.index(True))

            elif escape:
                escape_index = self.pause_popups.escape_button_index
                self.pause_popups.index_button(escape_index)

        # Save to determine if mouse buttons are held for the next frame
        self.last_mouse_state = self.mouse_state[:]

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
            self._loot_info_banner(text)
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
        item.reset(self.player)
        self.log_weapons()

        # Show info banner:
        if self.loot_overlay.banner:
            text = f"{string['loot']['backpack1']} {item.name} {string['loot']['backpack2']}" \
                if slot == "backpack" else f"{string['loot']['equip']} {item.name}!"

            self._loot_info_banner(text)
        self.loot_overlay = None

    def _loot_info_banner(self, text):
        looted_banner = Banner(
            text=text,
            size=BASE_SIZE * 2,
            position=self.box.center[:],
            color=c(colors["inventory_better"]),
            max_width=self.box.width,
            lifetime=3
        )
        self.particles.append(looted_banner)

    def draw(self):
        draw_group = []

        # Draw all characters
        for character in self.characters:

            drawn_pairs = character.draw(freeze=self.paused, no_bars=self.decorative)

            # Respect screenshake:
            if self.shake_v:
                drawn_new = []
                for pair in drawn_pairs:
                    surf, placement = pair
                    new_placement = (v(placement[:2]) + self.shake_v)
                    drawn_new.append((surf, new_placement))

                draw_group.extend(drawn_new)
            else:
                draw_group.extend(drawn_pairs)

            # Spawn dust clouds under rolling or ramming characters
            try:
                if character.hitbox and character.rolling > 0 or character.ramming:
                    # Spawn on average 10/s for standard size:
                    if random.random() < 10*FPS_TICK*character.size/BASE_SIZE:
                        self.particles.append(DustCloud(random.choice(character.hitbox)))
            except AttributeError:
                pass

        # Draw damage kickers, dead bodies and other particles:
        exhausted = []
        for particle in self.particles:

            # Remains are returning lists of tuples:
            if isinstance(particle, Remains):
                drawn_remains = particle.draw(pause=self.paused)

                # Respect screenshake:
                if self.shake_v:
                    drawn_new = []
                    for pair in drawn_remains:
                        surf, placement = pair
                        new_placement = (v(placement[:2]) + self.shake_v)
                        drawn_new.append((surf, new_placement))
                    drawn_remains = drawn_new

                draw_group.extend(drawn_remains)

            # Everything else returns tuples or nothing:
            else:
                drawn = particle.draw(pause=self.paused)
                if drawn:
                    # Respect screenshake if particle is shakeable (e.g. Banners stay static):
                    if self.shake_v and particle.shakeable:
                        draw_group.append((drawn[0], v(drawn[1][:2]) + self.shake_v))
                    else:
                        draw_group.append(drawn)
                    # If particle is outside bounds and not a Banner, despawn it
                    if not (drawn[1].colliderect(self.box) or isinstance(particle, Banner)):
                        exhausted.append(particle)

            if particle.lifetime <= 0:
                exhausted.append(particle)

        for particle in set(exhausted):
            self.particles.remove(particle)

        # Draw UI elements:
        if self.player:
            for ui in (self.player.inventory, self.progression):
                drawn = ui.draw()
                draw_group.append((drawn[0], v(drawn[1][:2]) + self.shake_v) if self.shake_v else drawn)

        # Draw pause surfaces
        if self.pause_popups:
            pause_ensemble = self.pause_popups.display(self.mouse_target, active=not bool(self.menus))
            if pause_ensemble:
                draw_group.extend(pause_ensemble)
            else:
                self.pause_popups = None

        if self.loot_overlay:
            draw_group.append(self.loot_overlay.draw())

            # Draw helper:
            if self.draw_helper:
                draw_group.extend(self.loot_overlay.helper.draw())

        # Draw menus:
        mouse_on_button = False
        expired_menus = []
        if self.menus:
            for menu in self.menus:
                draw_group.extend(menu.display(mouse_v=self.mouse_target, active=menu == self.menus[-1]))
                mouse_on_button = mouse_on_button or any(
                    button.rect.collidepoint(self.mouse_target) for button in menu.buttons_list
                )
                if not menu.buttons_list and not menu.decoration_objects:
                    expired_menus.append(menu)

        for menu in expired_menus:
            self.menus.remove(menu)

        # If mouse is hovering over the scene, show equipped weapons and stat cards
        # Unless any of the buttons are moused over in menus or pause popup:
        if self.pause_popups:
            mouse_on_button = mouse_on_button or any(
                button.rect.collidepoint(self.mouse_target) for button in self.pause_popups.buttons_list
            )

        if self.paused and not mouse_on_button:

            if self.box.collidepoint(self.mouse_target):
                displayed = False
                for character in self.characters:

                    if displayed:
                        break

                    for equipment in character.drawn_equipment:
                        if character.drawn_equipment[equipment].collidepoint(self.mouse_target):
                            draw_group.append(equipment.loot_cards[None].draw(position=self.mouse_target))
                            displayed = True
                            break

                    if displayed:
                        break

                    # If no equipment overlaps, try to display statcard instead:
                    for rect in character.hitbox:
                        if rect.collidepoint(self.mouse_target):
                            draw_group.append(character.stat_cards[None].draw(position=self.mouse_target))
                            displayed = True
                            break

        # In both pause and loot overlay, if mouse is hovering over inventory rects, show loot cards
        if self.player and (
                any((self.paused, self.loot_overlay)) and
                self.player.inventory.rect.collidepoint(self.mouse_target)
        ):
            mouse_in_inv = v(self.mouse_target) - v(self.player.inventory.rect.left, self.player.inventory.rect.top)
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
                        armament.loot_cards[compare_armament] = LootCard(armament, compare_to=compare_armament)

                    draw_group.append(armament.loot_cards[compare_armament].draw(
                        position=self.mouse_target,
                        draw_compared=True
                    ))

        # Display hitboxes if Tab is toggled
        if self.display_debug:
            for character in self.characters:
                for hand in character.weapon_slots:
                    hitbox = character.slots[hand].hitbox()
                    if hitbox and hitbox[0] and hitbox[1]:
                        hilt = r(*hitbox[0], 10, 10)
                        tip = r(*hitbox[1], 10, 10)
                        pygame.draw.rect(self.window, (255, 0, 0), hilt)
                        pygame.draw.rect(self.window, (0, 255, 0), tip)

                for hitbox in character.hitbox:
                    pygame.draw.rect(self.window, (255, 255, 0), hitbox, width=2)

                if character.ai:
                    topleft = character.position + character.body_coordinates[character.ai.slot] - \
                              v(character.ai.stab_reach_rx, character.ai.stab_reach_ry)
                    reach_rect = r(topleft, (character.ai.stab_reach_rx * 2, character.ai.stab_reach_ry * 2))

                    if character.facing_right:
                        angle_range = -math.pi / 2, +math.pi / 2
                    else:
                        angle_range = +math.pi / 2, -math.pi / 2

                    pygame.draw.arc(
                        self.window,
                        (64, 0, 0),
                        reach_rect,
                        *angle_range,
                        width=2
                    )

                    strategy = ascii_draw(BASE_SIZE // 2, character.ai.strategy, c(255, 0, 0))
                    state = ascii_draw(BASE_SIZE // 2, character.state, c(255, 0, 0))
                    strategy_place = character.position.x, character.position.y - BASE_SIZE * 3
                    strategy_rect = strategy.get_rect(center=strategy_place)
                    state_place = character.position.x, character.position.y - BASE_SIZE * 4
                    state_rect = state.get_rect(center=state_place)
                    draw_group.append((strategy, strategy_rect))
                    draw_group.append((state, state_rect))

            global fps_querried_time
            global fps_count

            fps_querried_time += CLOCK.get_time()
            if fps_querried_time >= 1000:
                fps_count = ascii_draw(40, str(int(CLOCK.get_fps())), (255, 255, 0))
                fps_querried_time = 0
            self.window.blit(fps_count, (0, 0))

        # Draw held mouse if exists
        if self.held_mouse is not None:
            draw_group.append(self.held_mouse.draw(v(self.mouse_target)))

        if self.draw_group_append:
            draw_group.extend(self.draw_group_append)
            self.draw_group_append = []

        try:
            pygame.display.update(self.window.blits(draw_group, doreturn=1))
        except ValueError as error:
            [print(pair) for pair in draw_group]
            raise ValueError(error)

        CLOCK.tick(FPS_TARGET)

    def collide(self):
        """
        Collide all weapons with all weapons and character hitboxes with other collision groups. Return set of contact
        pairs that must be processed.
        """
        # 0. List of weapons is extracted and ordered. It is stored in Scene.weapons.
        # 1. Each frame, the list is copied and iterated over
        iteration_list = self.colliding_weapons.copy()
        collision_quintet = []  # Hitting weapon, target, target's owner
        already_hit = []  # Do not iterate over each weapon more than once

        def log_colision(weapon_1, weapon_owner, victim, victim_owner, contact_point):
            collision_quintet.append((weapon_1, weapon_owner, victim, victim_owner, contact_point))
            already_hit.extend([weapon_1, victim])

        for character in filter(lambda x: not x.phasing, self.characters):  # Player weapons are iterated over first
            # Check if disabled characters have a particle associated with them; if not, spawn one:
            if character.state in DISABLED and character.immune_timer <= 0:
                has_particle = any(filter(
                    lambda x: isinstance(x, Stunned) and x.character == character,
                    self.particles
                ))
                if not has_particle:
                    self.particles.append(Stunned(character))

            if character in set(already_hit) or character.ignores_collision():
                continue

            target_characters = [
                char for char in self.characters
                if char.collision_group != character.collision_group and
                char != character and not char.ignores_collision()
            ]

            # Don't check weapons of disabled characters:
            if character.state not in DISABLED:
                for weapon in iteration_list[character]:
                    # Don't iterate over non-dangerous, disabled or deflected weapons:
                    if (
                            (not weapon.dangerous and abs(weapon.angular_speed) < SWING_THRESHOLD * 0.5) or
                            weapon.disabled or
                            not weapon.hitbox() or
                            weapon in set(already_hit) or
                            (isinstance(weapon, Pointed) and weapon.kebab)
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
                        try:
                            kebab = weapon.kebab
                            if foe == kebab:
                                continue
                        except AttributeError:
                            pass

                        for target_weapon in iteration_list[foe]:

                            # Not all weapons can parry
                            if not weapon.can_parry:
                                break

                            # 1 Frame = 1 hit
                            if (
                                    target_weapon in set(already_hit) or
                                    target_weapon.disabled or
                                    not target_weapon.hitbox() or
                                    not weapon.can_parry
                            ):
                                continue

                            # If hitboxes intersect, extend output pairs and add both to already_hit
                            try:
                                if intersect_lines(weapon.hitbox(), target_weapon.hitbox()):
                                    collision_point = (weapon.hitbox()[0][0] + weapon.hitbox()[1][0]) // 2, \
                                                      (weapon.hitbox()[0][1] + weapon.hitbox()[1][1]) // 2
                                    weapon_cleared = True
                                    log_colision(weapon, character, target_weapon, foe, collision_point)
                                    break

                                # Intersect target weapon with tip trail
                                if tip_trail and intersect_lines(tip_trail, target_weapon.hitbox()):
                                    collision_point = (weapon.hitbox()[0][0] + weapon.hitbox()[1][0]) // 2, \
                                                      (weapon.hitbox()[0][1] + weapon.hitbox()[1][1]) // 2
                                    weapon_cleared = True
                                    log_colision(weapon, character, target_weapon, foe, collision_point)
                                    break
                            except TypeError:
                                # Sometimes hitbox may disappear for a frame after roll; this is normal
                                break

                    # If weapon was hit, skip attempt to hit characters
                    # Clear weapon if it's not dangerous, as it is not a threat to characters:
                    if not weapon.dangerous or weapon_cleared:
                        continue

                    # Now iterate over all characters bodies
                    for foe in target_characters:
                        if weapon_cleared:
                            break

                        # Ignore Players that were hit recently (or this frame)
                        if foe.immune_timer > 0:
                            continue

                        if foe in set(already_hit):
                            continue

                        if foe.phasing:
                            continue

                        # Skewered by weapon characters are not colliding with it:
                        try:
                            kebab = weapon.kebab
                            if foe == kebab:
                                continue
                        except AttributeError:
                            pass

                        # Attempt to collide with each of character's hitboxes:
                        for rectangle in foe.hitbox:
                            if rectangle.collidepoint(weapon.tip_v):
                                weapon_cleared = True
                                log_colision(weapon, character, foe, foe, weapon.tip_v)
                                break
                            try:
                                clipped_line = rectangle.clipline(tip_trail)
                                if clipped_line:
                                    weapon_cleared = True
                                    log_colision(weapon, character, foe, foe, clipped_line[0])
                                    break

                                # Swords and axes should also attempt to intersect with full hitbox length:
                                clipped_line = rectangle.clipline(weapon.hitbox())
                                if isinstance(weapon, Bladed) and clipped_line:
                                    weapon_cleared = True
                                    log_colision(weapon, character, foe, foe, clipped_line[0])
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
                            meatbag == character or
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
                        log_colision(character, character, meatbag, meatbag, character.position)

        # Now process collsions:
        for quintet in collision_quintet:
            weapon, owner, target, opponent, point = quintet

            # Process weapon hits
            if isinstance(weapon, Wielded):
                if isinstance(target, Character):
                    collision_v = target.speed + weapon.tip_delta
                    damage = round(weapon.deal_damage(vector=collision_v, victim=target, victor=owner))
                    survived, actual_damage = opponent.hurt(
                        damage=damage,
                        vector=weapon.tip_delta,
                        weapon=weapon,
                        offender=owner
                    )
                    if not survived:
                        self.undertake(target)
                    # Cause FOF reaction in bots
                    elif actual_damage > 0:
                        play_sound('hurt', actual_damage * 0.01)
                        self.alert_ai(target)

                    elif isinstance(target.shielded, Shield):
                        shield = target.shielded
                        # Spawn sparks from shield
                        for _ in range(random.randint(7, 10)):
                            spark = Spark(
                                position=point,
                                weapon=shield,
                                vector=weapon.tip_delta / 2,
                                attack_color=shield.color,
                                angle_spread=(-45, 45)
                            )
                            self.particles.append(spark)

                        # If player was hit or performed the hit, add small screenshake:
                        if self.player == target:
                            # Wielding lighter shield causes heavier screenshake:
                            self.shaker.add_shake(0.001 * damage * (10-shield.weight))
                            play_sound('shield', 0.01 * damage)
                        elif self.player == owner:
                            self.shaker.add_shake(0.0025 * damage)
                            play_sound('shield', 0.005 * damage)

                    # Spawn kicker and blood:
                    self.splatter(point, target, actual_damage, weapon)

                    # Half shakeup for crits and Executions, quarter for everything else
                    if owner == self.player:
                        if actual_damage == weapon.damage_range[1] or target.anchor_weapon is not None:
                            self.shaker.add_shake(0.005 * actual_damage)
                        else:
                            self.shaker.add_shake(0.0025 * actual_damage)

                elif isinstance(target, Wielded):
                    # If player is participating and both weapons are dangerous, shake the scene:
                    if (
                            OPTIONS["screenshake"] and
                            self.player in {owner, opponent} and
                            weapon.dangerous and
                            target.dangerous
                    ):
                        enemy_weapon = target if self.player == owner else weapon
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
                            spark = Spark(
                                position=point,
                                weapon=hitting_weapon,
                                vector=hitting_weapon.tip_delta / 2,
                                attack_color=hitting_weapon.color
                            )
                            self.particles.append(spark)
                else:
                    raise ValueError(f"What are we hitting again? {target}")

            # Process body checks
            elif isinstance(weapon, Character) and isinstance(target, Character):
                # Reorder colliding agents if target is ramming:
                if target.ramming:
                    weapon, owner, target, opponent = target, opponent, weapon, owner

                collision_v = weapon.position - target.position

                # Shield hits processed here
                if weapon.collision_group != target.collision_group and weapon.ramming and not target.immune_timer > 0:
                    shield = weapon.slots["off_hand"]

                    # Calculate collision vector
                    collision_v = v(weapon.speed) * weapon.weight / target.weight

                    # Shield damage is static, push target for remaining charge duration + 0.5 s
                    survived, bash_damage = target.hurt(
                        damage=shield.deal_damage(v()),
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

                    self.splatter(target.position, target, bash_damage, shield)
                    self.shaker.add_shake(1.0)

                    for _ in range(random.randint(5, 7)):
                        spark = Spark(
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
                        (target.immune_timer <= 0) and (weapon.immune_timer <= 0)
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

                        damage_modifier = lerp((0.25 * POKE_THRESHOLD*POKE_THRESHOLD, POKE_THRESHOLD*POKE_THRESHOLD),
                                               relative_v.length_squared())
                        impact_damage = 0.05 * weapon.weight * damage_modifier
                        play_sound('collision', 0.01 * impact_damage)

                        # Cap impact damage at 15% of target health:
                        impact_damage = min(impact_damage, target.pct_cap*target.max_hp)

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
                        weapon.speed *= 0.5 * weapon.weight/target.weight

                else:
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
                    self.shaker.add_shake(equipment.weight*0.125)
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
                    (character.ai is None and character.immune_timer > 0)
            ):
                character.wall_collision_v = v()
                continue

            damage_modifier = lerp((0.25 * POKE_THRESHOLD * POKE_THRESHOLD, POKE_THRESHOLD * POKE_THRESHOLD),
                                   character.wall_collision_v.length_squared())
            impact_damage = 0.025 * character.weight * damage_modifier
            play_sound('collision', 0.01*impact_damage)

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
            self.shaker.add_shake(character.size / 2*BASE_SIZE)
            character.wall_collision_v = v()

    def splatter(self, point, target, damage, weapon=None):
        if damage == 0:
            return

        # Spawn kicker
        kicker = Kicker(
            point,
            damage,
            color=colors["dmg_kicker"],
            weapon=weapon,
            critcolor=colors["crit_kicker"]
        )
        self.particles.append(kicker)

        if target.has_blood and not OPTIONS["red_blood"] == 2:
            # Spawn a blood particle 50% of the time for each 7 damage suffered
            # Spawn 1 instantly always:
            first_blood = Droplet(point, target, spawn_delay=0)
            self.particles.append(first_blood)

            for _ in range(int(damage // 7)):
                if random.random() > 0.5:
                    continue

                blood = Droplet(point, target)
                self.particles.append(blood)
        else:
            # Spawn Sparks of body color
            for _ in range(int(damage // 7)):
                if random.random() > 0.5:
                    continue

                if weapon:
                    vector = weapon.tip_delta * -4
                else:
                    vector = v()
                    vector.from_polar((
                        2*POKE_THRESHOLD,
                        random.uniform(-180, 180)
                    ))
                blood = Spark(target.position, vector, attack_color=target.color, angle_spread=(-60, 60))
                self.particles.append(blood)

        if target == self.player:
            self.shaker.add_shake(damage*0.01)

    def undertake(self, character):
        play_sound('death', character.size/BASE_SIZE)
        character.hp = -1

        friends_alive = any(filter(
            lambda x: x.collision_group == character.collision_group and x != character,
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

        self.particles.append(Remains(character.kill(), self.box, particle_dump=self.particles))
        self.log_weapons()
        self.alert_ai(character)

    def iterate(self):
        # May happen when scene is handed over:
        # if player is specified, and not in dead characters, make sure it is in characters
        if self.player and self.player not in self.dead_characters and self.player not in self.characters:
            self.characters = [self.player] + self.characters
            self.log_weapons()

        # Calculate shake vector
        if OPTIONS["screenshake"]:
            self.shake_v = self.shaker.get_current_v()
        else:
            self.shaker.reset()
            self.shake_v = v()

        # Draw bg:
        self.window.fill(colors["base"])
        filling_rect = self.box.move(self.shake_v)
        pygame.draw.rect(surface=self.window, rect=filling_rect, color=DISPLAY_COLOR)

        # Iterate scene:
        self.update_input()
        self.draw()
        if not (self.paused or self.loot_overlay):
            self.collide()

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
            if OPTIONS["music"] and SceneHandler.active.theme and not pygame.mixer.music.get_busy():
                pygame.mixer.music.unpause()

    def spawn(self, monster, position_v=None):

        # High agility and flexibility monsters may roll in instead of jumping
        roll_in = monster.agility > 1.2 and random.random() < max(monster.ai.flexibility, 0.5)

        def roll_position(left=False):
            # Offset from center
            x_offset = random.uniform(self.box.width // 3, self.box.width // 4)
            if left:
                x_offset *= -1

            position = v(
                self.box.left + self.box.width // 2 + + x_offset,
                self.box.top + random.randint(self.box.height // 4, self.box.height * 3 // 4)
            )

            return position

        # Spawn away from the player, or at random if player is absent
        if self.player is not None:
            spawn_left = self.player is not None and self.player.position.x > self.box.left + self.box.width * 0.5
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
            roll_from_v.x = self.box.left - off_screen_x if spawn_left else self.box.right + off_screen_x
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
                jump_x = position_v.x - self.box.left + off_screen_x
            else:
                jump_x = position_v.x - self.box.right - off_screen_x

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

        play_sound('respawn', 1)
        self.shaker.add_shake(0.5)
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
            self.pause_popups = PauseEnsemble(self)
            self.paused = True

            # Update stat cards for every character
            for character in self.characters:
                for compare_key in character.stat_cards:
                    character.stat_cards[compare_key].redraw()

            # Reduce theme music volume:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.set_volume(0.2)

        # Spawn countdown to unpause, unless it is already in scene particles:
        elif OPTIONS["unpause_countdown"] != 0 and not any(
                True
                for countdown in self.particles
                if isinstance(countdown, CountDown) and countdown.action == self.hard_unpause
        ):
            self.pause_popups.fade()
            self.particles.append(CountDown(
                self.hard_unpause,
                {},
                colors["pause_popup"],
                position=self.box.center[:],
                go_text="GO!" if OPTIONS["unpause_countdown"] == 2 else None,
                ignore_pause=True,
                total_duration=OPTIONS["unpause_countdown"]
            ))

        else:
            self.pause_popups = None
            self.hard_unpause()

    def count_enemies_value(self):
        if self.player is None:
            return 0

        return sum(
            enemy.difficulty
            for enemy in (
                filter(
                    lambda x: x.collision_group != self.player.collision_group,
                    self.characters
                )
            ))

    def item_drop(self, character, dropped_item, slot=None, equip=True):
        # Animate remains
        if dropped_item:
            self.particles.append(Remains(
                [dropped_item.drop(character)],
                self.box,
                particle_dump=self.particles
            ))

        # Equip nothing in slot if it was occupied:
        if equip:
            character.equip(Nothing(), slot or dropped_item.preferred_slot)

        self.log_weapons()

    def echo(self, character, text, color):
        offset = v(3 * BASE_SIZE, -4 * BASE_SIZE) if character.position.x < self.box.center[0] \
            else v(3 * BASE_SIZE, 4 * BASE_SIZE)

        self.particles.append(
            SpeechBubble(
                offset,
                c(color),
                character,
                text
            )
        )

    def hard_unpause(self):
        # Restore theme music volume:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.set_volume(MUSIC_VOLUME)
        self.paused = False

    def generate_menu_popup(self, menu_class, keywords=None):
        if keywords is None:
            keywords = dict()
        self.menus.append(menu_class(**keywords))

    def request_new_handler(self, scene_handler, args=None, kwargs=None):
        args = args or []
        kwargs = kwargs or dict()
        self.new_sh_hook = scene_handler(*args, **kwargs)


# Supplemental drawing elements
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
            slot_name_surf = ascii_draw(BASE_SIZE//2, string["slot_names"][slot], colors["inventory_text"])
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
                    style=' ♥♡ ',
                    predetermined=content.durability
                )
                bar_surf, bar_rect = durability.display(content.durability)
                bar_left = (self.slot_rects[slot].width - bar_rect.width)//2
                bar_rect.move_ip(bar_left + self.slot_rects[slot].left, BASE_SIZE//2 + 3)
                surface.blit(bar_surf, bar_rect)

            # 3. Write down weapon class and tier
            class_string = f'{content.builder["class"]}'
            class_surf = ascii_draw(BASE_SIZE // 2, class_string, colors["inventory_text"])
            class_rect = class_surf.get_rect(left=self.slot_rects[slot].left + BASE_SIZE//2)

            tier_string = f'{string["tier"]} {content.tier}'
            tier_surf = ascii_draw(BASE_SIZE//2, tier_string, colors["inventory_text"])
            tier_rect = tier_surf.get_rect(bottomright=self.slot_rects[slot].bottomright)

            surface.blit(tier_surf, tier_rect)
            surface.blit(class_surf, class_rect)

        self.surface = surface

    def draw(self):
        return self.surface, self.rect


class LootOverlay:
    def __init__(
            self,
            loot_list: list,
            character: Character,
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
        self.helper = LootOverlayHelp()

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
            content: dict,
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
        self.content = content

        # Initiate:
        default_values = [(0 if isinstance(element, Bar) else False) for element in self.content]
        self.update(default_values)

    def update(self, values: list):
        self.surface.fill(self.base_color)
        # Draw from top and right:
        x, y = self.rect.width - self.offset, self.offset

        for i in range(len(self.content)):
            name, graphic = list(self.content.items())[i]
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
        text_rect = text_surface.get_rect(center=v(self.rect.center)-v(self.rect.topleft))
        text_surface_moused = ascii_draw_rows(size, [[row, colors["inventory_text"]] for row in self.mouse_over_text])
        text_moused_rect = text_surface_moused.get_rect(center=v(self.rect.center)-v(self.rect.topleft))
        disabled_surface = ascii_draw_rows(size, [[row, colors["inventory_description"]] for row in self.text])

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
        self.box = SceneHandler.active.scene.box
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
        trivia_banner = Banner(
            text=f"{string['gameplay']['trivia_label']}: {random.choice(string['trivia'])}",
            position=trivia_bottomleft,
            color=colors["inventory_description"],
            **info_string
        )

        # Tip string above trivia string
        trivia_banner_top = trivia_banner.surface.get_rect(bottomleft=trivia_bottomleft).top
        tip_banner = Banner(
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
    """Stolen from BamboozleChess."""

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
                if self.title.get_width() > right-left:
                    left = (WINDOW_SIZE[0]-self.title.get_width()) // 2
                    right = left + self.title.get_width()

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

        # Add tip and trivia if needed:
        self.tnt = TNT() if add_tnt else None

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


class OptionsMenu(Menu):
    def fade(self):
        # Write options dict to json file
        with open(os.path.join('options', 'options.json'), 'w') as options_json:
            json.dump(OPTIONS, options_json, sort_keys=False, indent=2)
        super(OptionsMenu, self).fade()

    def toggle(self, key):
        # Toggle an option and cause redrawing all buttons
        if isinstance(OPTIONS[key], bool):
            OPTIONS[key] = not OPTIONS[key]
        else:
            # Get possible options count from localization file
            options_count = len(string['menu']['option_contents'][key+'_states'])
            OPTIONS[key] = (OPTIONS[key] + 1) % options_count
        self.redraw()

        # Special scripts:
        if key == 'fullscreen':
            # Windowed mode grabs mouse by default
            OPTIONS["grab_mouse"] = True
            update_screen()
        elif key == "music":
            if not OPTIONS["music"]:
                end_theme()
            elif SceneHandler.active.theme:
                SceneHandler.active.play_theme()
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
                option_state_text = string['menu']['option_contents'][key+'_states'][str(OPTIONS[key])]

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


class PauseEnsemble(Menu):
    def __init__(self, scene):

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
            action_keywords={"menu_class": OptionsMenu},
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
                    "action_parameters": [MainMenuSceneHandler]
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
        paused_banner = Banner(
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
        # Campaign button:
        campaign_button = Button(
            text=[string['menu']['campaign']],
            rect=DEFAULT_BUTTON_RECT,
            action=print,
            action_parameters=["Not implemented in demo! How did you reach here, anyway?"],
            kb_index=0
        )
        campaign_button.disabled = True

        # Skirmish button
        skirmish_button = Button(
            text=[string['menu']['skirmish']],
            rect=DEFAULT_BUTTON_RECT,
            action=self.scene.generate_menu_popup,
            action_keywords={
                "menu_class": Difficulty,
                "keywords": {"action": self._start_skirmish}
            },
            kb_index=1
        )

        # Options button:
        options_button = Button(
            text=[string['menu']['options']],
            rect=DEFAULT_BUTTON_RECT,
            action=self.scene.generate_menu_popup,
            action_keywords={"menu_class": OptionsMenu},
            kb_index=2
        )

        # Exit button
        exit_button = Button(
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
            kb_index=3
        )

        return [campaign_button, skirmish_button, options_button, exit_button]

    def __init__(self, scene):
        # Work within scene:
        self.scene = scene

        text = string["game_title"]
        decorated_rows = [[row, colors["inventory_title"]] for row in frame_text([text], style='┏━┓┗┛┃').splitlines()]
        row_length = len(decorated_rows[0][0])
        decorated_rows.append([string["game_subtitle"].rjust(row_length), colors["inventory_description"]])
        title_surface = ascii_draw_rows(BASE_SIZE, decorated_rows)

        super(MainMenu, self).__init__(
            self.generate_buttons(),
            reposition_buttons=(2, 2),
            background=True,
            title_surface=title_surface,
            add_tnt=True
        )

    def _start_skirmish(self, tier):
        self.scene.request_new_handler(scene_handler=SkirmishScenehandler, args=[tier])


class Victory(Menu):
    def __init__(
            self,
            scene,
            next_level_text=None,
            next_level_action=None,
            next_level_parameters=None,
            next_level_keywords=None
    ):

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
                    "action_parameters": [MainMenuSceneHandler]
                }
            },
            kb_index=index
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
        victory_string = random.choice(string['gameplay']['scene_clear'])
        statement_surface = ascii_draw(BASE_SIZE*2, victory_string, colors['inventory_better'])
        # 2. Form killed monsters list surface
        if scene.dead_characters:
            killed_monsters_count = dict()
            for enemy in scene.dead_characters:
                killed_monsters_count[enemy.class_name] = killed_monsters_count.get(enemy.class_name, 0) + 1

            colored_header_row = [[string["gameplay"]["monster_list"].ljust(20), colors["inventory_text"]]]

            content_rows = frame_text(
                [
                    f"{key_value[0]}: {key_value[1]}".ljust(15)
                    for key_value in
                    sorted(killed_monsters_count.items(), key=lambda x: -x[1])
                ],
                '━━━━━ '
            )

            colored_content_rows = [[row, colors["inventory_text"]] for row in content_rows.splitlines()]

            killed_monsters_surface = ascii_draw_rows(BASE_SIZE, colored_header_row+colored_content_rows)

        else:
            killed_monsters_surface = s((0, 0))

        total_title_surface = s(
            (
                max(statement_surface.get_width(), killed_monsters_surface.get_width()) + BASE_SIZE * 2,
                BASE_SIZE * 3 + statement_surface.get_height() + killed_monsters_surface.get_height()
            ),
            pygame.SRCALPHA
        )
        frame_surface(total_title_surface, colors['inventory_text'])
        total_title_surface.blit(statement_surface, (BASE_SIZE, BASE_SIZE))
        total_title_surface.blit(killed_monsters_surface, (BASE_SIZE, BASE_SIZE*2 + statement_surface.get_height()))

        super().__init__(
            buttons_list=buttons_list,
            title_surface=total_title_surface,
            reposition_buttons=(1, len(buttons_list)),
            escape_button_index=menu_button.kb_index,
            add_tnt=True
        )


class Defeat(Menu):

    def __init__(self, scene):
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
                    "action_parameters": [MainMenuSceneHandler]
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

        defeat_banner = Banner(
            string['gameplay']['game_over'],
            BASE_SIZE * 2,
            v(scene.box.center[:]) - v(0, scene.box.height//3),
            colors["game_over"],
            lifetime=30,
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
    def __init__(self, action):

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
            reposition_buttons=(index+1, 1),
            background=True,
            title_surface=title_surface
        )


# Player character class
class Player(Humanoid):
    hit_immunity = 1.2

    def __init__(self, position, species='human'):
        player_body = character_stats["body"][species].copy()
        player_body["agility"] *= 2

        super(Player, self).__init__(
            position,
            **player_body,
            **colors["player"],
            faces=character_stats["mind"][species],
            name=string["protagonist_name"]
        )
        self.flip(new_collision=0)
        self.seen_loot_drops = False
        self.inventory = Inventory(self, INVENTORY_SPACE)

    def push(self, vector, time, state='flying', affect_player=False, **kwargs):
        # Player character is more resilient to pushback
        if affect_player and state in DISABLED:
            vector *= 0.33
        super().push(vector, time, state, **kwargs)

    def equip_basic(self, main_hand_pick=None, off_hand_pick=None):

        if main_hand_pick is None:
            main_hand_lst = list(
                filter(
                    lambda x:
                        artifacts[x]["class"] in {"Dagger", "Sword", "Spear", "Falchion", "Axe"} and
                        artifacts[x]["tier"] == 0,
                    artifacts
                )
            )
            main_hand_pick = random.choice(main_hand_lst), 'main_hand'
        else:
            main_hand_pick = main_hand_pick, 'main_hand'

        if off_hand_pick is None:
            off_hand_lst = list(
                filter(
                    lambda x:
                        artifacts[x]["class"] in {"Shield", "Swordbreaker", "Katar"} and
                        artifacts[x]["tier"] == 0,
                    artifacts
                )
            )
            off_hand_pick = random.choice(off_hand_lst), 'off_hand'
        else:
            off_hand_pick = off_hand_pick, 'off_hand'

        for weapon in (main_hand_pick, off_hand_pick):
            weapon_gen = Wielded.registry[artifacts[weapon[0]]["class"]]
            generated = weapon_gen(BASE_SIZE, equipment_dict=artifacts[weapon[0]], roll_stats=False)
            self.equip(generated, weapon[1])


# Scene Handlers: 'brains' of Scenes
class SceneHandler:
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
            player: Player = None,
            scene: Scene = None,
            enemy_color=c(100, 0, 0),
            spawn_delay: float = (8.0, 2.0),
            sort_loot: bool = False,
            no_player: bool = False,
            next_level_options: dict = None
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
            self.player = Player(position=PLAYER_SPAWN)
            self.player.equip_basic()
        else:
            self.player = player

        # Initiate a new scene, again, if needed:
        self.scene = scene or Scene(self.player, SCREEN, SCENE_BOUNDS)

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
        while enemy_cost < monster_total_cost:
            monster_instance = random.choices(pad_monster_classes, pad_monster_weights)[0]
            enemy_cost += monster_instance.difficulty
            # Insert in random spots EXCEPT for last: may contain Bosses
            insert_idx = random.randint(0, len(self.monsters) - 1) if self.monsters else 0
            self.monsters.insert(
                insert_idx,
                monster_instance(position=None, tier=self.tier, team_color=enemy_color)
            )

        # Create backlog of loot
        # Spread by slot:
        loot_by_slot = dict()
        for loot_class in tuple(Wielded.registry.values()):
            if loot_class.prefer_slot in loot_by_slot:
                loot_by_slot[loot_class.prefer_slot].append(loot_class)
            else:
                loot_by_slot[loot_class.prefer_slot] = [loot_class]

        loot_slots = list(loot_by_slot.keys())
        loot_slot_weights = [LOOT_OCCURRENCE_WEIGHTS[slot] for slot in loot_slots]

        self.loot = []

        last_loot_classes = [None, None]
        for _ in range(3 * loot_drops):
            # Choose slot to generate piece of loot for:
            loot_classes = loot_by_slot[random.choices(population=loot_slots, weights=loot_slot_weights)[0]]
            # Prevent generating 3 of same class in a row:
            if last_loot_classes[0] == last_loot_classes[1] in loot_classes:
                loot_classes.remove(last_loot_classes[0])
            loot_class = random.choice(loot_classes)

            # Cycle last 2 classes:
            last_loot_classes.pop()
            last_loot_classes.append(loot_class)

            # Append loot piece
            self.loot.append(loot_class(tier_target=tier, size=BASE_SIZE))
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
        self.spawn_queued: [None, Character] = None
        self.spawn_timer = 0

        # Own spawn delay
        self.respawn_banner: [None, Banner] = None
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

    def introduce_player(self):
        self.scene.player = self.player
        if self.player not in self.scene.characters:
            self.scene.characters = [self.player] + self.scene.characters
        self.fill_scene_progression()
        self.scene.log_weapons()

    def fill_scene_progression(self):
        bar_size = BASE_SIZE
        items = {
            f"{string['progression']['level']}{self.tier}": Bar(
                bar_size,
                10,
                colors["inventory_durability"],
                self.absolute_level_value,
                base_color=colors['inventory_durability']
            ),
            string['progression']['loot_drop']: Bar(
                bar_size,
                10,
                colors["inventory_durability"],
                self.loot_progression_required,
                base_color=colors['inventory_durability']
            ),
            "loot_drop": Indicator(ascii_draw(
                bar_size,
                string['progression']['loot_soon'],
                c(colors["indicator_good"])
            ))
        }
        self.scene.progression = ProgressionBars(items, font_size=bar_size)

    def batch_spawn(self, value=None):
        self.batch_spawn_after_loot = False
        if value is None:
            value = lerp(self.on_scren_enemies_value_range, self.relative_progression)

        # Stop if monster backlog is empty
        while self.monsters and self.scene.count_enemies_value() < value:
            self.spawn_monster(force=True)

    def execute(self):
        # 1. Iterate the scene
        self.scene.iterate()

        # 2. Affect the scene:
        # 2.1. Check and spawn monsters if needed
        # Check if loot is queued to be spawned
        if self.spawn_enemies and not any((self.loot_querried, self.scene.loot_overlay, self.scene.paused)):
            # If player just picked up loot, spawn bunch of monsters:
            if self.batch_spawn_after_loot:
                self.batch_spawn()
            # If scene is empty and player is chainkilling spawning enemies, spawn bunch at once:
            elif (self.scene.count_enemies_value() == 0 and self.scene.enemies_count_on_death == []) or (
                    len(self.scene.enemies_count_on_death) > 3 and
                    self.scene.enemies_count_on_death[-3:] == [0, 0, 0] and
                    self.scene.count_enemies_value() == 0
            ):
                self.batch_spawn()
            else:
                self.spawn_monster()

        # 2.2. Modify displayed scene bars according to progression
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
        if not self.scene.loot_overlay and self.loot_querried and self.scene.count_enemies_value() == 0 and not any([
            weapon
            for weapon in self.player.weapon_slots
            if self.player.slots[weapon] and self.player.slots[weapon].activation_offset != v()
        ]):
            self.batch_spawn_after_loot = True
            loot_package = self.loot[:3]
            del self.loot[:3]

            # Loot label contains a hint if it's first in playthrough:
            loot_label = random.choice(
                string["gameplay"]["loot_label" if self.player.seen_loot_drops else "loot_label_first"]
            )
            self.player.seen_loot_drops = True

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
            not self.player,
            self.monsters,
            self.scene.paused,
            self.loot_querried,
            self.spawn_queued,
            self.scene.loot_overlay,
            any(char for char in self.scene.characters if char.collision_group != self.player.collision_group)
        ])

        # Spawn victory menu
        if done and not any(victory for victory in self.scene.menus if isinstance(victory, Victory)):
            self.scene.menus.append(Victory(self.scene, **self.next_level_options))

        # 4. If scene requests a new handler, hand over:
        self._process_handover()

        # Return True unless scenario is completed
        return not done

    def _process_handover(self):
        if self.scene.new_sh_hook is not None:
            self.hand_off_to(self.scene.new_sh_hook)

    def spawn_monster(self, force=False):
        # If forced, immediately spawn a monster. Exception unsafe!
        if force:
            self.scene.spawn(self.monsters.pop())
            return

        # Calculate current progression dependent variables:
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
            self.spawn_timer -= iteration_tick if tick_down_speed == 1 else 2*iteration_tick

        # If there are less enemies than needed and no spawn is queued, queue one
        elif self.spawn_queued is None and present_enemies_value < current_on_scren_enemies and any(self.monsters):
            self.spawn_queued = self.monsters.pop()
            self.spawn_timer = current_spawn_delay

    def death_sequence(self, respawn_bang=True):

        if any(defeat for defeat in self.scene.menus if isinstance(defeat, Defeat)):
            return

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
                animation='slide',
                max_width=WINDOW_SIZE[0]*2
            )
            self.scene.particles.append(report_banner)

            if not self.player_survived:
                self.scene.menus.append(Defeat(self.scene))
                # Exit the loop
                return

            banner_text = random.choice(string['gameplay']['respawn_successful'])
            play_sound('player_death', 1)
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

    def hand_off_to(self, scene_handler, give_player=True):
        if self != SceneHandler.active:
            raise ValueError(f"{self} is not the active scene handler.")

        # Fade all menus:
        [menu.fade() for menu in self.scene.menus]

        # Tick down all banners:
        for banner in self.scene.particles:
            if isinstance(banner, Banner):
                banner.tick_down = True

        # Transplant scene banners and menus and player.
        scene_handler.scene.particles.extend(banner for banner in self.scene.particles if isinstance(banner, Banner))
        scene_handler.scene.menus.extend(self.scene.menus)

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
        play_theme(os.path.join('music', self.theme))


class SkirmishScenehandler(SceneHandler):
    theme = 'blkrbt_ninesix.ogg'

    def __init__(self, tier: int, *args, player=None, **kwargs):

        pad_monster_classes = list(Character.registry.values())
        pad_monster_weights = [monster_class.skirmish_spawn_rate for monster_class in pad_monster_classes]

        # Custom loot offering screens for newly spawning player:
        self.offer_off_hand = self.offer_main_hand = player is None
        player = player or Player(position=PLAYER_SPAWN)  # Base scene handler would equip player automatically

        super().__init__(
            tier=tier,
            *args,
            player=player,
            pad_monster_classes=pad_monster_classes,
            pad_monster_weights=pad_monster_weights,
            **kwargs
        )

        # Make sure Victory Screen has button to go to the next difficulty level
        if tier < 4:
            self.next_level_options = {
                "next_level_text": f"{string['menu']['difficulty']}: {tier+1}",
                "next_level_action": self.scene.request_new_handler,
                "next_level_parameters": [SkirmishScenehandler],
                "next_level_keywords": {
                    "kwargs": {
                        "tier": tier+1,
                        "player": self.player,  # Make sure the player is handed over!
                        **kwargs
                    }
                }
            }

        # If no custom loot drops are needed, pause monster spawning, and add a unpause countdown:
        self.spawn_enemies = False
        if not any((self.offer_main_hand, self.offer_off_hand)):
            self.scene.particles.append(CountDown(
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

    def execute(self):
        # If no custom loot drops are needed, proceed as normal:
        if not any((self.offer_main_hand, self.offer_off_hand)):

            # Spawn enemies if there is no countdown to do so:
            if not any(countdown for countdown in self.scene.particles if isinstance(countdown, CountDown)):
                self.spawn_enemies = True

            return super(SkirmishScenehandler, self).execute()

        # Usual processing:
        self.fill_scene_progression()
        self.scene.iterate()
        self._process_handover()

        # Offer basic selection of artefacts for weapon slots:
        if self.scene.loot_overlay is None and self.offer_main_hand:
            self._skirmish_init_equip('main_hand')
            self.offer_main_hand = False
        elif self.scene.loot_overlay is None and self.offer_off_hand:
            self._skirmish_init_equip('off_hand')
            self.offer_off_hand = False

        return False

    def _skirmish_init_equip(self, slot):
        weapon_classes = set(filter(
            lambda cls: Wielded.registry[cls].prefer_slot == slot,
            Wielded.registry.keys()
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
            generator = Wielded.registry[artifacts[artifact]["class"]]
            loot_package.append(generator(BASE_SIZE, equipment_dict=artifacts[artifact], roll_stats=False))

        # Loot label contains a hint if it's first in playthrough:
        loot_label = random.choice(string["gameplay"]["loot_label_arena"])
        self.player.seen_loot_drops = True

        self.scene.loot_overlay = LootOverlay(
            loot_package,
            self.player,
            label=loot_label,
            appear_from=None,
            sound=False,
            banner=False
        )


class MainMenuSceneHandler(SceneHandler):
    _spawn_delay = 2
    _gladiator_capacity = 8
    theme = 'blkrbt_brokenlight.ogg'

    def __init__(self):

        self.challenger_classes = [gladiator for gladiator in Character.registry.values() if not gladiator.debug]
        self.spawned_collision_group = 1
        self.spawn_timer = 0

        # Create a custom scene
        main_menu_scene = Scene(None, SCREEN, EXTENDED_SCENE_BOUNDS, decorative=True)

        super(MainMenuSceneHandler, self).__init__(
            tier=0,
            pad_monster_classes=[],
            monster_total_cost=0,
            loot_drops=0,
            no_player=True,
            scene=main_menu_scene
        )

        # Spawn MainMenu in the scene
        self.scene.menus.append(MainMenu(self.scene))

    def execute(self):
        # Spawn a monster if less than N are present
        if len(self.scene.characters) < self._gladiator_capacity and self.spawn_timer <= 0:
            challenger_tier = random.choice(range(1, 5))
            new_challenger = random.choice(self.challenger_classes)(position=None, tier=challenger_tier)
            new_challenger.collision_group = self.spawned_collision_group
            self.monsters.append(new_challenger)
            self.spawn_monster(force=True)
            # Python is designed to to indefinetely extend integers, so there is no upper bound to catch exceptions for
            # Besides, increment is expected to be occuring once per dozen seconds, so it is not imaginable to reach
            # any kind of memory limit during time person stares at the menu.
            self.spawned_collision_group += 1
            self.spawn_timer = self._spawn_delay
        else:
            self.spawn_timer -= FPS_TICK

        # 1. Iterate the scene
        self.scene.iterate()
        self._process_handover()

        # Main Menu is never completed
        return False
