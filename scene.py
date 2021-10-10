# todo:
#  pause_ensemble with tips and trivia/unpause countdown
#  bots "scream" about their important intentions (fleeing, attacking)
#  display combo counter
#  weapon parries and blocked hits have chance to trigger FOF in high flexibility characters
#  ?? Picking nothing restores some durability to damaged weapon
#  ?? screenshake
# After tech demo
# todo: when mousing over loot cards in loot overlay, show compared cards
# todo: cut off all surfaces by bounding box
# todo: Add lightning effect to character spawn
# todo: draw complex background

from ui import *
from equipment import *
from particle import *
import sys

# Display FPS counters(initial state):
fps_querried_time = 1000
fps_count = ascii_draw(40, '0', (255, 255, 0))


class Scene:
    """Takes Rect as bounding box, list of enemies and a player"""

    def __init__(self, player, window, bounds, enemies=None, progression=None):
        self.window = window
        self.box = bounds

        # Spawn player:
        self.player = player
        if self.player:
            self.inventory = Inventory(self.player, INVENTORY_SPACE)
        else:
            self.inventory = None

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

        # Store damage kickers and other particles
        self.particles = []

        # Store display for level progress:
        self.progression = progression

        # Reserved for pause popups and banners:
        self.pause_popups = None
        self.loot_overlay = None
        self.draw_helper = False
        self.draw_group_append = []

    def log_weapons(self):
        for character in self.characters:
            self.colliding_weapons[character] = []
            for slot in character.weapon_slots:
                weapon = character.slots[slot]
                if weapon.hitbox():
                    self.colliding_weapons[character].append(weapon)

        if self.inventory:
            self.inventory.update()

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

        spacebar, debug, wheel = False, False, False
        number_keys = [False]*9

        for event in pygame.event.get():  # User did something

            if event.type == pygame.QUIT:  # If user closed the window
                pygame.quit()  # We are done so we exit this loop
                sys.exit()

            if event.type == pygame.MOUSEWHEEL:
                wheel = True

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.toggle_pause()

                if event.key == pygame.K_TAB:
                    self.display_debug = not self.display_debug

                if event.key == pygame.K_SPACE:
                    spacebar = True

                if event.key == pygame.K_f:
                    debug = True

                # Get pressed number keys
                for index_key in enumerate(range(pygame.K_1, pygame.K_9)):
                    number_keys[index_key[0]] = (event.key == index_key[1])

        self.mouse_target = v(pygame.mouse.get_pos())
        self.mouse_state = pygame.mouse.get_pressed(num_buttons=3)
        keyboard = pygame.key.get_pressed()

        # Digest held buttons input:
        movement = keyboard[pygame.K_w], keyboard[pygame.K_a], keyboard[pygame.K_s], keyboard[pygame.K_d]
        shift = keyboard[pygame.K_LSHIFT]

        # Debug:
        if debug:
            # print("No debug action set at the moment.")
            # self.echo(self.player, "Geronimo!", colors["lightning"])
            # self.player.slots['main_hand']._spin(-3*SWING_THRESHOLD, 360 * 3)
            morph_equipment(self.player)

        # Normal input processing:
        if not self.paused and not self.loot_overlay:

            # Start channeling flip
            if spacebar and self.player in self.characters:

                # If character is hurt, flip is instant:
                if self.player.immune_timer > 0:
                    self.player.flip()
                else:
                    self.player.channel(self.player.flip_time, self.player.flip, {})

            # Start channeling weapon switch
            if wheel and self.player in self.characters and self.player.slots["backpack"]:
                # Duration depends on agility mod of backpack weapon
                switch_time = self.player.flip_time * 0.75 * self.player.slots["backpack"].agility_modifier
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
                        # Spawn dust clouds
                        for _ in range(int(char.weight*0.02)):
                            self.particles.append(DustCloud(char.position))
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
        if wheel and self.loot_overlay:
            self.player.backpack_swap(scene=self)
            self.loot_overlay.redraw_loot()

        # Process clicks and keypresses on loot overlay
        self.draw_helper = False
        if self.loot_overlay:
            if self.loot_overlay.rect.collidepoint(self.mouse_target):
                # Draw help around the mouse:
                self.draw_helper = True

                # Pass mouse click to loot overlay:
                result = self.loot_overlay.catch(self.mouse_target, self.mouse_state)
                if all(result):
                    self._from_loot_overlay(*result)

                    # Middle click closes overlay
                    if self.mouse_state[1]:
                        self.loot_overlay = None

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
                            ascii_draw(BASE_SIZE*2//3, f"[Equipped]", colors["inventory_title"]),
                            (self.loot_overlay.offset*0.5, self.loot_overlay.offset*0.5)
                        )
                        self.draw_group_append.append([card_surface, card_rect])

                # Fully heal player no matter the picked option:
                self.player.hp, self.player.stamina = self.player.max_hp, self.player.max_stamina

            if any(number_keys):
                result = self.loot_overlay.catch_index(number_keys.index(True))
                self._from_loot_overlay(*result)

        # Allow to drop weapons in pause or loot overlay:
        if (self.loot_overlay or self.paused) and self.inventory.rect.collidepoint(self.mouse_target):

            # Can't drop last damaging weapon:
            not_last_weapon = len(list(filter(
                lambda x: self.player.slots[x],
                self.player.weapon_slots + ['backpack']
            ))) > 1

            if not_last_weapon and self.held_mouse is None and self.mouse_state[0]:

                # Spawn a held_mouse object that will drop from inventory
                for slot in self.inventory.slot_rects:
                    modified_target = v(self.mouse_target) - v(self.inventory.rect.left, self.inventory.rect.top)
                    if (
                            self.inventory.slot_rects[slot].collidepoint(modified_target) and
                            self.player.slots[slot]
                    ):
                        self.held_mouse = HeldMouse(
                            execute=self.item_drop,
                            options_dict={
                                "character": self.player,
                                "dropped_item": self.player.slots[slot],
                                "slot": slot
                            },
                            text=f"DROP {SLOT_NAMES[slot].upper()}"
                        )

        # Handle procession and deletion of HeldMouse object:
        if self.held_mouse is not None:
            if not self.mouse_state[0] or self.held_mouse.hold():
                self.held_mouse = None

        # Save to determine if mouse buttons are held for the next frame
        self.last_mouse_state = self.mouse_state[:]

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
        self.loot_overlay = None

        # Show info banner:
        text = f"Stashed Tier {item.tier} {item.builder['class'].lower()} in backpack!" if \
            slot == "backpack" else \
            f"Equipped Tier {item.tier} {item.builder['class'].lower()}"

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
            draw_group.extend(character.draw(freeze=self.paused))

            # Spawn dust clouds under rolling or ramming characters
            try:
                if character.rolling > 0 or character.ramming:
                    # Spawn on average 10/s for standard size:
                    if random.random() < 10*FPS_TICK*character.size/BASE_SIZE:
                        self.particles.append(DustCloud(character.position))
            except AttributeError:
                pass

        # Draw damage kickers, dead bodies and other particles:
        exhausted = []
        for particle in self.particles:

            # Remains are returning lists of tuples:
            if isinstance(particle, Remains):
                draw_group.extend(particle.draw(pause=self.paused))
            # Everything else returns tuples or nothing:
            else:
                drawn = particle.draw(pause=self.paused)
                if drawn:
                    draw_group.append(drawn)
                    # If particle is outside bounds and not a Banner, despawn it
                    if not (drawn[1].colliderect(self.box) or isinstance(particle, Banner)):
                        exhausted.append(particle)

            if particle.lifetime <= 0:
                exhausted.append(particle)

        for particle in set(exhausted):
            self.particles.remove(particle)

        # Draw UI elements:
        for ui in (self.inventory, self.progression):
            draw_group.append(ui.draw())

        # Draw pause surfaces
        if self.pause_popups:
            draw_group.append(self.pause_popups.draw())
            if self.pause_popups.lifetime <= 0:
                self.pause_popups = 0

        if self.loot_overlay:
            draw_group.append(self.loot_overlay.draw())

        if self.paused:
            self.pause_popups.lifetime = max(self.pause_popups.animation_duration + FPS_TICK,
                                             self.pause_popups.lifetime)

            # If mouse is hovering over the scene, show equipped weapons and stat cards
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
        if any((self.paused, self.loot_overlay)) and self.inventory.rect.collidepoint(self.mouse_target):
            mouse_in_inv = v(self.mouse_target) - v(self.inventory.rect.left, self.inventory.rect.top)
            for slot in self.inventory.slot_rects:
                if self.inventory.slot_rects[slot].collidepoint(mouse_in_inv):
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
                    # Spawn mouse-hint particle for player Daggers roll
                    try:
                        if weapon.last_parry and not weapon.roll_particle:
                            offset = v(-2*BASE_SIZE, 0) if weapon.prefer_slot == 'main_hand' else v(2*BASE_SIZE, 0)

                            weapon.roll_particle = MouseHint(
                                relative_position=offset,
                                lifetime=weapon.roll_window,
                                text="ROLL!",
                                size=BASE_SIZE * 2 // 3,
                                color=c(colors["indicator_good"]),
                                monitor=weapon.has_roll
                            )
                            self.particles.append(weapon.roll_particle)

                    except AttributeError:
                        pass

                    # Don't iterate over non-dangerous, disabled or deflected weapons:
                    if (
                            (not weapon.dangerous and abs(weapon.angular_speed) < SWING_THRESHOLD * 0.5) or
                            weapon.disabled or
                            not weapon.hitbox() or
                            weapon in set(already_hit)
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
                            # 1 Frame = 1 hit
                            if (
                                    target_weapon in set(already_hit) or
                                    target_weapon.disabled or
                                    not target_weapon.hitbox()
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
                    if (
                            meatbag == character or
                            meatbag in set(already_hit) or
                            character in set(already_hit) or
                            character.ignores_collision() or
                            meatbag.ignores_collision()
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
                    # todo: 'SKEWERED!', 'BLEEDING!' etc. kicker
                    damage = round(weapon.deal_damage(vector=collision_v, victim=target, attacker=owner))
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

                    # Spawn kicker and blood:
                    self.splatter(point, target, actual_damage, weapon)

                elif isinstance(target, Wielded):
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

                    if not survived:
                        self.undertake(target)
                    # Cause FOF reaction in bots
                    else:
                        self.alert_ai(target)

                    self.splatter(point, target, bash_damage, shield)
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
                    if 4 * relative_v.length_squared() < POKE_THRESHOLD ** 2:
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

                        damage_modifier = lerp((0.25 * POKE_THRESHOLD ** 2, POKE_THRESHOLD ** 2),
                                               relative_v.length_squared())
                        impact_damage = 0.05 * weapon.weight * damage_modifier

                        # Cap impact damage at 15% of target health:
                        impact_damage = min(impact_damage, 0.15*target.max_hp)

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
                    collision_v.scale_to_length(POKE_THRESHOLD)
                    if not (weapon.shielded or weapon.anchor_timer > 0):
                        weapon.push(collision_v, 0.2, 'active')
                    if not (target.shielded or weapon.anchor_timer > 0):
                        target.push(-collision_v, 0.2, 'active')

            else:
                raise ValueError(str(weapon) + " is not a valid collision agent")

        # Process dropped shields:
        for character in self.characters:
            for weapon_slot in character.weapon_slots:
                shield = character.slots[weapon_slot]
                try:
                    if shield.querry_destroy:
                        self.item_drop(character, shield, weapon_slot)
                        # Inform AI it no longer has a shield
                        character.shielded = None
                        self.log_weapons()
                except AttributeError:
                    continue

        # Process characters hitting walls:
        for character in filter(
            lambda x: x.wall_collision_v != v() and character.hp > 0,
            self.characters
        ):

            if character.wall_collision_v.length_squared() < 0.25 * POKE_THRESHOLD ** 2 or character.immune_timer > 0:
                character.wall_collision_v = v()
                continue

            damage_modifier = lerp((0.25 * POKE_THRESHOLD ** 2, POKE_THRESHOLD ** 2),
                                   character.wall_collision_v.length_squared())
            impact_damage = 0.025 * character.weight * damage_modifier

            # Cap at 15% max_hp
            impact_damage = min(impact_damage, 0.15 * character.max_hp)

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
            character.wall_collision_v = v()

    def splatter(self, point, target, damage, weapon=None):
        # Spawn kicker
        kicker = Kicker(
            point,
            damage,
            color=colors["dmg_kicker"],
            weapon=weapon,
            critcolor=colors["crit_kicker"]
        )
        self.particles.append(kicker)

        if target.has_blood:
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

    def undertake(self, character):

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
        self.particles.append(Remains(character.kill(), self.box, particle_dump=self.particles))
        self.log_weapons()
        self.alert_ai(character)

    def iterate(self):
        # Draw bg:
        self.window.fill(colors["base"])
        pygame.draw.rect(surface=self.window, rect=self.box, color=DISPLAY_COLOR)

        # Iterate scene:
        self.update_input()
        self.draw()
        if not (self.paused or self.loot_overlay):
            self.collide()

        # Prevent overflow
        pygame.event.pump()

        # Pause on losing focus:
        if not pygame.mouse.get_focused() and not (self.paused or self.loot_overlay):
            self.toggle_pause()

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

        spawn_left = self.player is not None and self.player.position.x > self.box.left + self.box.width * 0.5

        if spawn_left != monster.facing_right:
            monster.flip(dormant=True)

        if position_v is None:
            # Pick a random position in bounding box: horizontally between 2/3 and 5/6, vertically between 1/4 and 3/4
            position_v = roll_position(left=spawn_left)

        # If there is a character near target position, reroll position_v
        clear = not any((meatbag.position - position_v).length_squared() < 9 * BASE_SIZE for meatbag in self.characters)
        while not clear:
            position_v = roll_position(left=spawn_left)
            clear = not any((meatbag.position - position_v).length_squared() < BASE_SIZE ** 2
                            for meatbag in self.characters)

        off_screen_x = random.uniform(BASE_SIZE, 3 * BASE_SIZE)

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

    def toggle_pause(self, skip_banner=False):
        if not self.paused:

            if not skip_banner:
                self.pause_popups = Banner(
                    "[PAUSED]",
                    BASE_SIZE * 2,
                    self.box.center[:],
                    colors["pause_popup"],
                    lifetime=1.2,
                    animation_duration=0.3,
                    tick_down=False
                )

            # Update stat cards for every character
            for character in self.characters:
                for compare_key in character.stat_cards:
                    character.stat_cards[compare_key].redraw()

        elif self.paused and not skip_banner:
            self.pause_popups.tick_down = True

        self.paused = not self.paused

    def count_enemies_value(self):
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
