# todo:
#  Add orc equipment: Axes, Sword, Spear, Heavy Shield
#  teach AI to use axe whirlwind
# After tech demo
# todo:
#  ?? animate character flip
#  ?? Treasure goblins
#  hat oscillates instead oor together with face
#  Animal(Character) subclass
#   Monsters: Goblin, Wolf, Rat, Elf, Orc
#  ?? cache character_positions to be redrawn at most 10 times/s
#  generate equipment for Goblin, Elf, Orc
#  AI can use off-hand weapons, not just shields
# todo: celebration state if away from enemy and flexibility >> skill or all enemies dead
# todo: randomly exchange wait <=> to wander: move to a new position, not too close to arena edge
# todo: make goblins use appropriate swords: scavenged look a bit too chaotic

from base_class import *
from particle import AttackWarning
from equipment import Shield, Dagger, Spear, Sword, Bladed, Pointed, Falchion, Nothing
from typing import Any


class Humanoid(Character):
    weapon_slots = ["main_hand", "off_hand"]
    body_coordinates = {
        "face": [0, 0],
        "main_hand": [-40, 25],
        "off_hand": [50, 25],
        "hat": [5, -10],
        "bars": [0, -45]
    }

    def __init__(self, position, size, hand, *args, blink=5, **kwargs):
        super().__init__(position, size, *args, **kwargs)
        self.slots: dict[str, Any] = {
            "main_hand": Nothing(),
            "off_hand": Nothing(),
            "hat": Nothing(),
            "backpack": Nothing()
        }
        self.body_coordinates = Humanoid.body_coordinates.copy()
        scale_body(self.body_coordinates, size)

        # Randomize blink
        self.blink = blink
        self.blink_timer = self.blink * random.gauss(1.0, 0.1)

        # Add hands
        self.hand = pygame.transform.rotate(ascii_draw(self.size, hand, self.color), -180)
        self.hand_rect = self.hand.get_rect()

        # Ability to roll
        self.max_roll = 0
        self.rolling = 0
        self.rolled_through = []
        self.roll_cooldown = 0

    def do_blink(self):
        # Randomize next blink:
        self.blink_timer = self.blink * random.gauss(1.0, 0.1)

        self.state = random.choice(['blink', 'blink', 'idle_rare'])
        if self.state == 'idle_rare':
            self.state_timer = self.all_faces[self.state][-1]
        else:
            self.state_timer = 0.1

    def draw(self, body_only=False, freeze=False):
        return_list = super().draw(body_only=body_only)

        if self.state_timer < -self.blink_timer and self.state == 'idle':
            self.do_blink()

        # Modify placement by adding placement coordinates and relative offset from self.body_coordinates
        # 1. Draw face

        # Pick facial expression
        face_row = self.all_faces[self.visual_state]
        if face_row[-1] > 0:
            time_per_frame = face_row[-1] / (len(face_row) - 1)  # total time / faces number
            index = int(self.visual_timer / time_per_frame)
        else:
            index = 0

        face_pick = face_row[index]
        modified_center = v(self.position) + v(self.body_coordinates['face'])

        if self.max_roll != 0:
            # Animate roll according to progress
            # Rotation direction and value
            progress = 1-self.rolling/self.max_roll
            direction = -1 if self.speed.x >= 0 else +1

            # Increase Y coordinate for visual drop
            # Sine wave from 0 to π should make a good look
            modified_center.y += 1.5*self.size * math.sin(math.pi * progress)

            # Visually reduce face surface
            new_size = 1 - 0.3 * math.sin(math.pi * progress)

            face_pick = pygame.transform.rotozoom(face_pick, 360*progress*direction, new_size)

        if not freeze:
            modified_center[1] += -self.size * math.sin(self.life_timer * 2) * 0.15
        face_rect = face_pick.get_rect(center=modified_center)

        if self.immune_timer > 0:
            transparent_face = face_pick.copy()
            transparency = int(127 + 127 * math.sin(pygame.time.get_ticks() * 0.02))
            transparent_face.set_alpha(transparency)
            return_list.append((transparent_face, face_rect))
        else:
            return_list.append((face_pick, face_rect))

        # 2. Draw hat, if available
        if self.slots["hat"]:
            # todo: flip according to self.facing_right
            hat_center = self.position + v(self.body_coordinates['hat'])
            return_list.append(self.slots["hat"].draw(hat_center))

        # 3. Draw equipped aimed off-hand and main weapons
        for weapon in self.weapon_slots:

            if not body_only:
                output = self.slots[weapon].draw(self)
                if output:
                    # Remember where weapon is drawn for UI purposes
                    self.drawn_equipment[self.slots[weapon]] = output[1]

                    return_list.append(output[0:2])
                    # Weapons may also return additional sprites to draw: projectiles or weapon trails
                    # Put them on the bottom so that they are not drawn over character
                    try:
                        return_list = output[2] + return_list
                    except (IndexError, TypeError):
                        pass

            # 4. Also draw hand, if weapon allows it
            if not self.slots[weapon] or (self.slots[weapon] and not self.slots[weapon].hides_hand):

                if not self.slots[weapon] or not self.slots[weapon].hilt_v:
                    hand_location = v(self.position) + v(self.body_coordinates[weapon])
                else:
                    hand_location = v(self.slots[weapon].hilt_v)

                hand_angle = self.slots[weapon].last_angle

                hand_surface, hand_rect = rot_center(self.hand, hand_angle, hand_location)
                # I'm not sure hitbox should include hands. Creates a lot of accidental pushing.
                # self.hitbox.append(hand_rect)
                return_list.append((hand_surface, hand_rect))

        return return_list

    def backpack_swap(self, scene):
        backpack = self.slots["backpack"]
        if not backpack:
            return

        slot = backpack.prefer_slot

        self.slots["backpack"], self.slots[slot] = self.slots[slot], self.slots["backpack"]
        self.slots[slot].reset(self)

        # Inform the scene:
        scene.log_weapons()

    def roll(self, vector, roll_cooldown=0, duration=0.5):
        # Set constants:
        self.rolled_through = []
        self.anchor_timer = 0
        self.phasing = True
        self.max_roll = self.rolling = duration
        self.roll_cooldown = roll_cooldown

        # Push self in direction
        self.speed = v()
        self.push(vector, duration, 'active')

        # Lock weapons in same position
        # Animating them would *look* cooler, but would also made the feel much clunkier
        for slot in self.weapon_slots:
            weapon = self.slots[slot]
            if weapon:
                weapon.disabled = True
                weapon.lock(duration+0.2, angle=weapon.last_angle)

    def aim(self, target=None):
        super(Humanoid, self).aim(target)

        # Support for rolling
        if self.rolling >= 0:
            self.rolling -= FPS_TICK
        # Stop the roll
        elif self.max_roll != 0:
            self.phasing = False
            self.rolling = 0
            self.max_roll = 0
            self.anchor(0.2)
            # If we end up behind back of an enemy, instantly flip (unless we are already facing this direction):
            for foe in self.rolled_through:
                # Reset cooldown:
                self.roll_cooldown = 0
                if self.facing_right != (self.position.x < foe.position.x):
                    self.flip()
                    break

            # Show cooldown bar:
            if self.roll_cooldown > 0:
                self.bars["roll_cooldown"] = Bar(
                    BASE_SIZE // 3,
                    10,
                    colors["bar_base"],
                    self.roll_cooldown,
                    base_color=colors["bar_base"],
                    show_number=False,
                    cache=False
                )

            # Prevent weapons from dealing absurd damage:
            for weapon in self.weapon_slots:
                try:
                    self.slots[weapon].tip_delta = v()
                    self.slots[weapon].angular_speed = 0
                except AttributeError:
                    continue

        # Tick down cooldown untill next roll
        else:
            if self.roll_cooldown <= 0:
                self.bars.pop("roll_cooldown", None)
            self.roll_cooldown = max(0, self.roll_cooldown - FPS_TICK)

    def move(self, direction_v, scene, limit=1.0):
        super(Humanoid, self).move(direction_v, scene, limit)
        # If we are rolling through, check what are we passing
        if self.phasing:
            for enemy in filter(lambda x: x.collision_group != self.collision_group, scene.characters):
                passing = []

                # Log enemy characters we passed through:
                for rect in enemy.hitbox:
                    if rect.collidelist(self.hitbox) != -1:
                        passing.append(enemy)
                        break

                for dodged in passing:
                    if dodged not in self.rolled_through:
                        self.rolled_through.append(dodged)

    def equip(self, armament, slot):
        # Allow to update constants
        armament.on_equip(self)

        # Equipping Nothing drops slot content
        if not armament:
            self.slots[slot], drop = Nothing(), self.slots[slot]
            return drop

        # Orient weapon
        armament.last_angle = armament.default_angle if self.facing_right else 180 - armament.default_angle

        # If slot is empty, just equip and drop Nothing
        if not self.slots[slot]:
            self.slots[slot] = armament
            return Nothing()

        # If available, move currently equipped item to backpack
        elif slot != 'backpack' and not self.slots['backpack']:
            self.slots[slot], self.slots['backpack'] = armament, self.slots[slot]
            return Nothing()

        # Otherwise equip over, drop original content
        self.slots[slot], drop = armament, self.slots[slot]
        return drop


class AI:
    def __init__(
            self,
            character,
            weapon_slot='main_hand',
            aggression=0.5,
            skill=0.5,
            flexibility=0.5,
            courage=0.5
    ):
        # What are we analyzing for:
        self.character = character
        self.scene = None
        self.slot = weapon_slot
        self.weapon = self.character.slots[self.slot]

        # Own psyche:
        self.aggression = aggression  # Likelihood of choosing aggressive strategy
        self.skill = skill  # Precision of own calculations and assessments
        self.flexibility = flexibility  # Likelihood of changing strategy often/early
        self.courage = courage  # Likelihood to keep up the aggression when low on HP and SP

        # Calculate how early to warn of own attack intent
        self.attack_delay = 0.2 + (1-self.skill) * 0.3

        # Dynamically changing scene assessment:
        self.target = None
        self.friends = {}
        self.enemies = {}

        self.strategy = "wait"
        self.strategy_timer = 0
        self.strategy_dict: dict = {}

        self.fof_time = 0

        # Change dynamically
        self.morale = 1.0
        self.speed_limit = 1.0

        # Own equipment assessments:

        # These constants are not subject to be randomized by skill function, as they are base
        self.tick_stamina_consumption = self.weapon.stamina_drain * 250 * FPS_TICK * self.weapon.aim_drain_modifier
        self.angular_acceleration = self.character.agility * self.weapon.agility_modifier * FPS_TICK * 6.7

        # Stab attack of Pointed weapon
        self.stab_reach_rx, self.stab_reach_ry = 0, 0
        self.stab_stamina_cost = 0

        # Swing attack is trickier
        self.swing_range = 0  # Max range(a.k.a. weapon length)
        self.swing_stamina_cost = 0  # What is stamina cost of accelerating weapon to SWING_TRESHOLD
        self.swing_windup_time = 0  # How long weapon must be moving from standstill to reach SWING_TRESHOLD
        self.swing_windup_angle = 0  # What is minimal angle windup is required to start swinging from standstill

        # Falchion roll
        self.roll_range = 0

        # Initial calculations:
        self.calculate_stab()
        self.calculate_swing()
        self.calculate_roll()

        # Introduce standard mistake: will be re-rolled each analysis
        self.error = self._skill_distribution()

    def roll_error(self):
        self.error = self._skill_distribution()

    def _skill_distribution(self, value=1.0):
        return value * random.gauss(1.0, 0.05 - self.skill * 0.2)

    def warn(self):
        warning_position = self.character.body_coordinates["bars"] + v(0, -2*BASE_SIZE)
        warning_particle = AttackWarning(warning_position, self.character, self.attack_delay)
        self.scene.particles.append(warning_particle)
        return warning_particle

    def set_strategy(self, strategy, follow_time):
        self.strategy = strategy
        self.strategy_timer = follow_time

        # Remove all own warnings from scene particles:
        for key in filter(lambda x: isinstance(self.strategy_dict[x], AttackWarning), self.strategy_dict):
            try:
                self.scene.particles.remove(self.strategy_dict[key])
            except ValueError:
                pass

        self.strategy_dict = {}

        # Special states:
        if strategy == 'wait':
            self.target = None

        elif strategy == "flee":
            self.character.set_state("scared", 5 / self.courage)
            # Fleeing restores morale
            self.morale = min(1.0, 0.5*self.courage + self.morale)

    def calculate_stab(self):
        if not isinstance(self.weapon, Pointed) or isinstance(self.weapon, Falchion):
            return

        # Calculate own max stab reach distance when equipping Pointed weapon
        max_speed_component = 0.2 * self.character.max_speed * FPS_TARGET

        stab_modifier = 2.5 * FPS_TICK * BASE_SIZE * self.character.agility * \
            self.weapon.stab_modifier * self.weapon.agility_modifier

        self.stab_reach_rx = self.weapon.length + 2 * max_speed_component + stab_modifier
        self.stab_reach_ry = self.weapon.length + 1.2 * max_speed_component + stab_modifier
        self.stab_stamina_cost = self.character.max_stamina * self.weapon.stab_cost

    def calculate_roll(self):
        if not isinstance(self.weapon, Falchion):
            return

        self.roll_range = 0.5 * self.weapon.character_specific["roll_treshold"] * FPS_TARGET

    def calculate_swing(self):
        if not isinstance(self.weapon, Bladed):
            return

        self.swing_range = self.weapon.length
        self.swing_windup_time = SWING_THRESHOLD * FPS_TICK / self.angular_acceleration
        self.swing_stamina_cost = self.swing_windup_time * (FPS_TARGET * self.tick_stamina_consumption)
        self.swing_windup_angle = 0.5 * FPS_TARGET * self.angular_acceleration * (self.swing_windup_time ** 2)

    def effective_range(self):
        # Returns assessment of own effective range in direction of target from own weapon hilt
        swing_range = 0
        stab_range = 0
        if self.target is None:
            return None

        if self.stab_reach_rx > 0:
            stab_range = 0.5 * (self.stab_reach_rx + self.stab_reach_ry)

        return max(swing_range, stab_range)

    def in_stab_range(self):
        """Return True if a stab executed right now would hit"""
        # Get vector to where a stab ends
        # 1. Inertia component (replicates calculation from equipment):
        if self.character.speed == v():
            if self.character.facing_right:
                inertia_vector = v(1, 0)
            else:
                inertia_vector = v(-1, 0)
        else:
            inertia_vector = v(self.character.speed)

        inertia_distance = 1.25 * BASE_SIZE * self.character.agility * self.weapon.stab_modifier *\
            self.weapon.agility_modifier
        inertia_vector.scale_to_length(inertia_distance)
        if inertia_vector.x > 0 != self.character.facing_right:
            inertia_vector.x *= 0.25

        # 2. Add speed component AND target speed and stab inertia
        cumulative_v = self.error * (inertia_vector + (self.character.speed-self.target.speed) * FPS_TARGET * 0.2)

        # 3. Move from original tip position
        stab_vector = self.weapon.tip_v + cumulative_v

        contact = any(rect.collidepoint(stab_vector) for rect in self.target.hitbox)
        return contact

    def analyze(self, scene, initial=False):
        if self.character not in set(scene.characters):
            raise KeyError("I'm not in the scene! Check dead characters")

        # Re-roll
        self.roll_error()

        # There is a small chance to just start rushing in, ignoring all distractions
        # Characters with high courage, aggression and low flexibility may choose this approach.
        # We'll call this "Rhino factor". It has 12 seconds of duration, but likely to be overriden early by
        # either hitting or getting hit.

        # Default AI has 5% chance to fall to Rhino factor
        if self.target and 0.1 * self.aggression * self.courage > random.uniform(0, self.flexibility):
            self.set_strategy("charge", 12)
            self.strategy_dict["FULL RHINO"] = True

        # General situation awareness:
        self.scene = scene
        self.enemies = {}
        self.friends = {}
        own_health = min(self.character.hp / self.character.max_hp, self.character.stamina / self.character.max_stamina)

        # Count enemies, assess their health and assume their weapon reach:
        for enemy in filter(lambda x: x.collision_group != self.character.collision_group, self.scene.characters):
            # Ignore enemies with no hitbox:
            if not enemy.hitbox:
                continue

            weapon_slot = enemy.weapon_slots[0]
            enemy_weapon = enemy.slots[weapon_slot]

            if not enemy_weapon:
                reach = 0
            elif isinstance(enemy_weapon, Pointed):
                reach = enemy_weapon.length * 1.1 + v(enemy.body_coordinates[weapon_slot]).length()
            else:
                reach = enemy_weapon.length + v(enemy.body_coordinates[weapon_slot]).length()

            health = min(enemy.hp / enemy.max_hp, enemy.stamina / enemy.max_stamina)

            distance = (enemy.position - self.character.position - self.character.body_coordinates[self.slot]).length()

            self.enemies[enemy] = {
                "distance": distance,
                "reach": reach,
                "health": max(health, 0.01),
                "shield": enemy.shielded,
                "weapon": enemy_weapon
            }

            # Identify closest target
            if self.target is None or distance < self.enemies[self.target]["distance"] and enemy.hp > 0:
                self.target = enemy

        # No enemies? We wait.
        if not self.enemies:
            self.set_strategy('wait', 3 - random.uniform(0, 2 * self.flexibility))
            return

        # Assess effective distance to target:
        desired_sparring_distance = max(self.effective_range(), self.enemies[self.target]["reach"]) * 1.2

        # Count friends and assess their state:
        for friend in filter(
                lambda x: x != self.character and x.collision_group == self.character.collision_group,
                self.scene.characters
        ):
            weapon_slot = friend.weapon_slots[0]
            weapon = friend.slots[weapon_slot]
            if isinstance(weapon, Pointed):
                reach = weapon.length * 1.5 + v(friend.body_coordinates[weapon_slot]).length()
            else:
                reach = weapon.length + v(friend.body_coordinates[weapon_slot]).length()

            health = max(
                min(friend.hp / friend.max_hp, friend.stamina / friend.max_stamina),
                0.01
            )

            if friend.ai is not None:
                ai_state = friend.ai.strategy
            else:
                ai_state = 'unknown'

            distance = (friend.position - self.character.position).length()

            self.friends[friend] = {
                "distance": distance,
                "reach": reach,
                "health": max(health, 0.01),
                "strategy": ai_state
            }

        # Pick strategy depending on above factors:

        if initial:
            # If we just enter the scene, override strategy assessment
            self.set_strategy("wait", 6 - random.uniform(0, 2 * self.flexibility))
            return

        # Count friends that are ALL of the following:
        #   1. Locked on same target
        #   2. Close to the target
        #   3. Healthy (by own courage standards)
        #   4. Not passive
        count_allies = 0
        for friend in self.friends:
            if self.friends[friend]["strategy"] in PASSIVE_STRATEGY:
                continue

            if all([
                friend.ai.target == self.target,
                self.friends[friend]["health"] >= self.courage,
                self.friends[friend]["distance"] <= self.enemies[self.target]["distance"] * 1.5
            ]):
                count_allies += 1

        # Test if we have a subplan:
        if "next" in self.strategy_dict:
            self.set_strategy(*self.strategy_dict["next"])
            return

        # If we are too far from the target, move in:
        elif desired_sparring_distance * 1.2 < self.enemies[self.target]["distance"]:
            self.set_strategy("confront", 5 - random.uniform(0, 2 * self.flexibility))
            return

        # Elif we are around desired distance from the target, either keep position or attack:
        elif desired_sparring_distance < self.enemies[self.target]["distance"] * 1.2:

            # Test if we have enough stamina for swing or stab attack:
            if (self.stab_stamina_cost and self.character.stamina < self.stab_stamina_cost) or \
                    (self.swing_stamina_cost and self.character.stamina < self.swing_stamina_cost):
                violence = False

            # Test if target is shielded and character is not too eager:
            elif isinstance(self.target.shielded, Shield) and \
                    random.uniform(0, self.aggression) > random.uniform(0, self.skill):
                violence = False

            # Test if target "looks" healthier than we are, possibly chicken out
            elif own_health / self.enemies[self.target]["health"] < random.uniform(0, self.courage):
                violence = False

            # Decide if we enter aggressive state, based on game state. If decision is negative, repeat
            # decision process for every ally, until positive conclusion is reached or we ran out of allies:
            else:
                violence = False
                agression_chance = self.aggression * self.morale * self.character.stamina / self.character.max_stamina
                for _ in range(count_allies + 1):
                    violence = random.random() < agression_chance
                    if violence:
                        break

            if violence:
                # Attempt to strike:
                self.set_strategy("charge", 3 - random.uniform(0, 2 * self.flexibility))
                return

            # Failing all that, keep wary:
            self.set_strategy("confront", 5 - random.uniform(0, 2 * self.flexibility))
            return

        # Else, decide if we want to "dogfight" if we have clear advantage or fall back to "confront"
        else:
            # Test if our weapon is suited for CQC:
            if not isinstance(self.weapon, Bladed):
                violence = False

            # Test if we have enough stamina for swing attack:
            elif self.swing_stamina_cost and self.character.stamina < self.swing_stamina_cost:
                violence = False

            # Test if target is shielded and self is not too eager:
            elif isinstance(self.target.shielded, Shield) and \
                    random.uniform(0, self.aggression) > random.uniform(0, self.skill):
                violence = False

            # Test if we are behind the target that faces same way:
            elif (
                    self.character.facing_right ==
                    self.target.facing_right ==
                    self.character.position.x < self.target.position.x
            ):
                violence = True

            # Now test if enemy weapon is not suited for CQC while our is; needs flexibility check:
            elif not isinstance(self.enemies[self.target]["weapon"], Bladed) and \
                    isinstance(self.weapon, Bladed) and \
                    self.flexibility > random.random():
                violence = True

            # Test if target "looks" healthier than we are, possibly chicken out
            elif own_health / self.enemies[self.target]["health"] < random.uniform(0, self.courage):
                violence = False

            # Decide if we enter aggressive state, based on game state. If decision is negative, repeat
            # decision process for every ally, until positive conclusion is reached or we ran out of allies:
            else:
                violence = False
                agression_chance = self.aggression * self.morale * self.character.stamina / self.character.max_stamina
                for _ in range(count_allies + 1):
                    violence = random.random() < agression_chance
                    if violence:
                        break

            if violence:
                # Attempt to stay in range and continue aggression:
                self.set_strategy('dogfight', 5 - random.uniform(0, 2 * self.flexibility))
                return

            # Failing all that, return to safe range:
            self.set_strategy("confront", 5 - random.uniform(0, 2 * self.flexibility))
            return

    def execute(self):

        """Modify own behavior depending on state; returns movement direction vector and aiming target"""
        self.strategy_timer -= FPS_TICK
        self.fof_time += FPS_TICK
        if self.strategy_timer <= 0:
            self.analyze(self.scene)

        # If we are channeling something already, keep at it:
        if self.character.channeling:
            return v(), None

        # Assess distance to other characters. Use squares to avoid sqrt
        distances = {}
        for body in filter(lambda x: x != self.character, self.scene.characters):
            # Consider hitboxes centers for simplicity
            minimal_distance = 0
            for own_rectangle in self.character.hitbox:
                for other_rectangle in body.hitbox:
                    if not minimal_distance:
                        minimal_distance = rect_distance(own_rectangle, other_rectangle)
                    else:
                        minimal_distance = min(
                            minimal_distance,
                            rect_distance(own_rectangle, other_rectangle)
                        )
            distances[body] = minimal_distance

        # If we are ever behind enemy back-to-back, change strategy to reroute
        if self.strategy != 'reroute' and self.target and \
                (self.character.position.x >= self.target.position.x) == self.character.facing_right:
            self.set_strategy("reroute", 5)

        # Used in multiple calculations
        try:
            actual_distance_vector = self.target.position - self.character.position
        except AttributeError:
            actual_distance_vector = v()

        if self.strategy == 'wait':
            self.speed_limit = 0.25
            # If enemy moves towards self with tangible speed, wake up and assess situation
            # Only if we are not just spawning in:
            if self.character.state != 'jumping' or self.character.phasing:
                for enemy in filter(
                        lambda x: x.collision_group != self.character.collision_group and x.hitbox,
                        self.scene.characters
                ):
                    if (enemy.speed.x > 0 == self.character.facing_right) and abs(enemy.speed.x) > POKE_THRESHOLD * 0.5:
                        if "waking_up" not in self.strategy_dict:
                            self.strategy_dict['waking_up'] = random.random() * self.flexibility

            if 'waking_up' in self.strategy_dict:
                self.strategy_dict['waking_up'] -= FPS_TICK
                if self.strategy_dict['waking_up'] <= 0:
                    self.analyze(self.scene)

            directions = v(), None

        elif self.strategy == 'charge':
            self.speed_limit = 1.0

            if self.target in self.scene.dead_characters:
                self.analyze(self.scene)
                return self.execute()

            # Parried? Switch to confront
            if self.weapon.disabled:
                self.strategy_dict["next"] = 'confront', 5 - random.uniform(0, 2 * self.flexibility)
                self.analyze(self.scene)
                return self.execute()

            # Test if self and target has other characters between us
            try:
                to_target_v = self.target.position - self.character.position
            except AttributeError:
                # Skip frame until positions are recalculated
                return v(), None

            for body in filter(lambda x: x not in {self.character, self.target}, self.scene.characters):
                # 1. Angle is sharp:
                to_obstruction_v = body.position - self.character.position
                if not -45 < to_target_v.angle_to(to_obstruction_v) < 45:
                    continue

                # 2. Distance is greater than body's main hitbox width
                try:
                    margin2 = body.hitbox[0].width ** 2
                except IndexError:
                    # Characters without a hitbox???
                    continue

                projection_v = to_target_v * (body.position.dot(to_target_v)) / to_target_v.length_squared()
                height2 = (to_target_v - projection_v).length_squared()
                if not height2 > margin2:
                    self.set_strategy("confront", 5 - random.uniform(0, 2 * self.flexibility))
                    return self.execute()

            # For anything Pointed
            if self.stab_stamina_cost > 0:
                self.strategy_dict["plan"] = "stab"
                # If stab is already planned, check warning time lifetime:
                if "warning" in self.strategy_dict:
                    # If warning time ran out:
                    if self.strategy_dict["warning"].lifetime <= 0 and self.character.stamina > self.stab_stamina_cost:
                        # Execute stab:
                        self.character.use(self.slot, continuous_input=False)
                        self.strategy_dict.pop("warning")
                        # Fix follow time, to guarantee reassessment after the stab is over, even if it misses
                        self.strategy_timer = 0.2

                elif self.character.stamina > self.stab_stamina_cost and self.in_stab_range():
                    # Spawn warning and use it's lifetime as counter before the attack
                    self.strategy_dict["warning"] = self.warn()
                    self.strategy_dict["timestamp"] = pygame.time.get_ticks()

                # Otherwise, clear own intent to attack
                else:
                    self.set_strategy('charge', max(self.strategy_timer, 0))

            # For falchions, roll in:
            elif self.roll_range > 0:
                self.strategy_dict["plan"] = "roll in"
                # ?? Todo: high skill may attempt to roll through the player
                # If we are close, switch to dogfight:
                if distances[self.target] <= 1.2 * self.swing_range:
                    # Immediately switch to dogfight
                    self.strategy_dict["next"] = ('dogfight', 5 - random.uniform(0, 2 * self.flexibility))
                    self.analyze(self.scene)

                # If we are 2 roll ranges away from enemy or closer, roll in for some personal time
                elif distances[self.target] <= 2 * self.roll_range:
                    # Ready up dogfight
                    self.strategy_dict["next"] = ('dogfight', 5 - random.uniform(0, 2 * self.flexibility))
                    # Execute roll:
                    self.character.use(self.slot, continuous_input=False, point=self.target.position)

            else:
                raise ValueError(f"{self.weapon} is missing charge logic")

            # We need to actively oppose any tangential movement:
            radial_v = actual_distance_vector.normalize()

            # 1. Project own speed on radial_v
            projection_angle = self.character.speed.angle_to(radial_v)
            projected_v = v()
            projected_v.from_polar((1, projection_angle))
            # 2. Get character.speed component that is perpendicular
            tangential_speed = self.character.speed - projected_v
            # 3. Create opposing vector as component for directions
            compensation_v = -tangential_speed.normalize()/2

            directions = radial_v + compensation_v, self.target.position

        elif self.strategy == 'confront':
            if self.target is None or self.target.hp <= 0:
                self.analyze(self.scene)
                return self.execute()

            self.speed_limit = 0.5 + 0.5 * self.courage
            # Check if we have something planned; else, re-evaluate a subplan
            substrategy = self.strategy_dict.get("plan", None)

            # Tick down timed subplans
            if 'timer' in self.strategy_dict:
                self.strategy_dict["timer"] -= FPS_TICK
                if self.strategy_dict["timer"] < 0:
                    # Trigger reevaluation
                    if 'next' not in self.strategy_dict:
                        substrategy = None
                    else:
                        self.analyze(self.scene)
                        return self.execute()

            if substrategy is None:
                # First, make sure we are at desired distance from the target
                # Distance is at least enemy reach, but not more than own reach
                # May stay outside own reach if enemy reach is longer
                # corridor is 0.8a < d < 1.2a
                desired_distance = max(self.effective_range(), self.enemies[self.target]["reach"])
                actual_distance = distances[self.target]
                if 0.8*actual_distance < desired_distance < 1.2*actual_distance:
                    # Roll for aggression, either prepare to charge or keep circling around target
                    agression_chance = self.aggression * self.morale * self.character.stamina /\
                        self.character.max_stamina
                    if random.random() < agression_chance and not isinstance(self.target.shielded, Shield):
                        self.strategy_dict["plan"] = "prepare"
                        substrategy = "prepare"
                        self.strategy_dict["timer"] = self.flexibility  # Keep attacks more or less predictable
                        self.strategy_dict["next"] = ("charge", 5)
                    else:
                        self.strategy_dict["plan"] = "circle"
                        substrategy = "circle"
                        self.strategy_dict["radius"] = distances[self.target]
                        self.strategy_dict["timer"] = 2 + random.uniform(0, self.flexibility)
                        # Find closest ally; pick clockwise/ccw direction to move AWAY from ally
                        try:
                            closest_friend = sorted(self.friends.keys(), key=lambda x: self.friends[x]["distance"])[0]
                            ccw = ccw_triangle(
                                self.target.position,
                                self.character.position,
                                closest_friend.position
                            )
                            # Move in OPPOSITE direction:
                            self.strategy_dict["ccw"] = not ccw
                        except IndexError:  # No friends =(
                            # Default to ccw
                            self.strategy_dict["ccw"] = True

                elif actual_distance < desired_distance:
                    # Move in straight line to desired distance(away from target)
                    self.strategy_dict["plan"] = 'kite'
                    self.strategy_dict["desired_distance"] = desired_distance
                    substrategy = "kite"
                    self.strategy_timer += 2 + random.uniform(0, self.flexibility)
                else:
                    # Move in straight line to desired distance(towards target)
                    self.strategy_dict["plan"] = 'chase'
                    self.strategy_dict["desired_distance"] = desired_distance
                    substrategy = "chase"
                    self.strategy_timer += 2 + random.uniform(0, self.flexibility)

            # Execute plan:
            if substrategy in {"kite", "chase"}:
                move = self.target.position - self.character.position

                if substrategy == "kite":
                    self.use_shield()
                    move *= -1

                aim = self.target.position

                # If we are in range, clear subplan for the future:
                if self.target not in distances:
                    self.analyze(self.scene)
                if 0.8 * distances[self.target] < self.strategy_dict["desired_distance"] < 1.2 * distances[self.target]:
                    self.strategy_dict = {}

                return move, aim

            elif substrategy == "circle":
                # First, create a radial vector to move towards target
                radius_v = (self.target.position - self.character.position).normalize()
                # Second, create a vector that is perpendicular to radius, depending on CCW direction
                target_angle = radius_v.as_polar()[1]
                # Acceptable bounds is [-45, 45] for right-facing; [135,-135] for left-facing
                if self.character.facing_right and target_angle > 45:
                    self.strategy_dict["ccw"] = True
                elif self.character.facing_right and target_angle < -45:
                    self.strategy_dict["ccw"] = False
                elif not self.character.facing_right and 0 > target_angle > -135:
                    self.strategy_dict["ccw"] = True
                elif not self.character.facing_right and 0 < target_angle < 135:
                    self.strategy_dict["ccw"] = False

                if self.strategy_dict["ccw"]:
                    # Turn left from inward:
                    rotation_v = radius_v.rotate(90)
                else:
                    # Turn right from outward:
                    rotation_v = radius_v.rotate(-90)

                if distances[self.target] < self.strategy_dict["radius"]:
                    radius_v *= -1

                    # If we own a shield, hold it up:
                    self.use_shield()

                return radius_v + rotation_v, self.target.position

            elif substrategy == "prepare":
                # We need to actively oppose any tangential movement:
                radial_v = actual_distance_vector.normalize()

                # 1. Project own speed on radial_v
                projection_angle = self.character.speed.angle_to(radial_v)
                projected_v = v()
                projected_v.from_polar((1, projection_angle))
                # 2. Get character.speed component that is perpendicular
                tangential_speed = self.character.speed - projected_v
                # 3. Create opposing vector as component for directions
                compensation_v = -tangential_speed.normalize()

                # Move to own reach distance if less; actively compensate for any tangential component.
                if actual_distance_vector.length_squared() < self.effective_range():
                    return radial_v + compensation_v, self.target.position
                else:
                    return compensation_v, self.target.position

            else:
                raise AttributeError("Can't find substrategy instructions for: " + repr(substrategy))

        elif self.strategy == 'reroute':
            self.speed_limit = 1.0
            self.strategy_dict["route_timer"] = self.strategy_dict.get("route_timer", self._skill_distribution(1.0))
            self.strategy_dict["route_timer"] -= FPS_TICK

            # Move horizontally opposing the enemy until we reach our max speed and channel a filp immediately after
            if self.character.facing_right:
                direction = 1
            else:
                direction = -1

            directions = v(direction, 0), None
            # Flip if reached max speed or ran for long enough
            if self.character.speed.x == math.copysign(self.character.max_speed, direction) or\
                    self.strategy_dict["route_timer"] < 0:
                self.character.channel(self.character.flip_time, self.character.flip, {})

        elif self.strategy == 'dogfight':
            self.speed_limit = 0.5
            # If at any point we run low on stamina, revert to confront, unless we are hitting already:
            if self.swing_stamina_cost > self.character.stamina and self.strategy_dict.get("stage", "aim") != "hit":
                self.set_strategy("confront", 5 - random.uniform(0, 2 * self.flexibility))
                return self.execute()

            # Parried? Switch to confront
            if self.weapon.activation_offset != v():
                self.strategy_dict["next"] = 'confront', 5 - random.uniform(0, 2 * self.flexibility)
                self.analyze(self.scene)
                return self.execute()

            # Current angle to target:
            angle_to_target = actual_distance_vector.as_polar()[1]

            # If we haven't planned a swing, start planning it:
            if "stage" not in self.strategy_dict:
                self.strategy_dict["stage"] = "aim"

                # Determine swing direction > away from targets angle:
                mt = min(90, self.weapon.max_tilt)
                if -90 < angle_to_target < 90:
                    self.strategy_dict["aim_angle"] = -math.copysign(mt, angle_to_target)
                    self.strategy_dict["hit_angle"] = math.copysign(mt, angle_to_target)
                elif 180 <= angle_to_target <= 90:
                    self.strategy_dict["aim_angle"] = -180 + mt
                    self.strategy_dict["hit_angle"] = 180 - mt
                else:
                    self.strategy_dict["aim_angle"] = -180 + mt
                    self.strategy_dict["hit_angle"] = 180 - mt

                # Remember the angle to target and stay to it:
                self.strategy_dict["target_relative_position"] = v(actual_distance_vector)

            if self.strategy_dict["stage"] == "aim":
                # Swing in predetermined direction, until weapon hits the max_tilt:
                aim_v = v()
                aim_v.from_polar((BASE_SIZE*5, self.strategy_dict["aim_angle"]))
                aim_v += self.character.position

                if abs(self.weapon.last_angle + self.strategy_dict["aim_angle"]) < 3:
                    self.strategy_dict["stage"] = "warn"
                    # Spawn warning
                    self.strategy_dict["warning"] = self.warn()
                    self.strategy_dict["timestamp"] = pygame.time.get_ticks()

            elif self.strategy_dict["stage"] == "warn":
                # Hold weapon still
                aim_v = v()
                aim_v.from_polar((10000, self.strategy_dict["aim_angle"]))
                aim_v += self.character.position

                if self.strategy_dict["warning"].lifetime <= 0:
                    # Start swinging:
                    self.strategy_dict["stage"] = "hit"
                    self.strategy_dict.pop("warning")
                    # Fix follow time, to guarantee reassessment after the stab is over, even if it misses
                    self.strategy_timer = 0.5

            elif self.strategy_dict["stage"] == "hit":
                self.speed_limit = 1.0
                aim_v = v()
                aim_v.from_polar((10000, self.strategy_dict["hit_angle"]))
                aim_v += self.character.position

            else:
                raise KeyError("Unknown dogfight swing stage!")

            # Attempt to keep exactly at saved relative position to target, unless in "hit" stage
            target_distance = 0
            for own_hitbox in self.character.hitbox:
                for enemy_hitbox in self.target.hitbox:
                    hitbox_distance = rect_distance(own_hitbox, enemy_hitbox)
                    if target_distance:
                        target_distance = min(hitbox_distance, target_distance)
                    else:
                        target_distance = hitbox_distance

            if self.strategy_dict["stage"] != "hit" and \
                    target_distance < 2.25*self.weapon.length**2:
                movement_v = v(actual_distance_vector)-v(self.strategy_dict["target_relative_position"])
            else:
                movement_v = v(actual_distance_vector)

            directions = movement_v, aim_v

        elif self.strategy == 'flee':

            # Log current position to see if we are making progress:
            if not self.character.channeling:
                currrent_position = self.character.position[:]
                if 'last_position' in self.strategy_dict:
                    if self.strategy_dict['last_position'] == currrent_position:
                        self.analyze(self.scene)
                self.strategy_dict['last_position'] = currrent_position

            # If target is gone, stop fleeing immediately
            if self.target is None:
                self.analyze(self.scene)
                return self.execute()

            self.speed_limit = 1.0
            # If we are facing the enemy and not within range, flip. Querry fleeing to keep being executed after
            # flip is complete
            try:
                if self.target and self.character.facing_right != self.target.facing_right and\
                        distances[self.target] > self.enemies[self.target]["reach"]:
                    self.character.channel(self.character.flip_time, self.character.flip, {})
                    self.strategy_dict["next"] = 'flee', self.strategy_timer
            except KeyError:
                pass

            directions = -actual_distance_vector, None

        else:
            # Placeholder!
            print(self.strategy, 'is boring! Charrrrge!')
            self.set_strategy('charge', 5)
            directions = self.target.position - self.character.position, self.target.position

        # Unless we are recklessly charging, avoid bumping into characters who are less than own weapon length away
        if self.strategy not in ATTACKING_STRATEGY:

            reach = self.weapon.length
            for body in distances:

                if distances[body] < reach:
                    avoid = v(self.character.position) - v(body.position)
                    directions = avoid, directions[1]
                    # Update circling direction:
                    if "ccw" in self.strategy_dict:
                        self.strategy_dict['ccw'] = not self.strategy_dict['ccw']

                    if body == self.target and self.strategy != 'dogfight':
                        # Consider fleeing, then consider aggression
                        self.fight_or_flight(victim=self.character)
                        self.fight_or_flight(victim=self.target)

        return directions

    def fight_or_flight(self, victim):
        """
        Takes an object in scene, either a hurt character or a parried weapon. Reaction can be either to charge in,
        start fleeing, querry up a state change, or analyze situation anew
        """
        # todo: weapon processing
        # Can't activate FOF too often:
        if self.fof_time < self.flexibility * 5:
            return

        # If we are busy, ignore
        if self.strategy in BUSY:
            return

        # If victim is target, and it's dead, switch to waiting:
        if victim == self.target and victim.hp <= 0:
            self.set_strategy("wait", 6 - random.uniform(0, 2 * self.flexibility))
            return

        # Reset timer for next FOF reaction
        self.fof_time = 0

        base_courage = self.courage * self.morale
        own_health = min(self.character.hp / self.character.max_hp, self.character.stamina / self.character.max_stamina)

        if isinstance(victim, Character):
            # Less courage if we are hit
            if victim == self.character:
                base_courage *= self.courage
            else:
                # Far away is less impactful
                distance_mod = self.scene.box.width * self.scene.box.height / \
                    (v(self.character.position) - v(victim.position)).length_squared()
                base_courage *= distance_mod

            # More courage if target is hit
            if victim == self.target:
                base_courage += (1-base_courage) * 2

            victim_collision = victim.collision_group

        elif isinstance(victim, Equipment):
            # Clashing weapons are less scary than wounds
            base_courage *= 2
            # Default:
            victim_collision = 0
            for char in self.scene.colliding_weapons:
                if victim in char.slots.values():
                    victim_collision = char.collision_group

        else:
            raise ValueError(f"{self} can't react to {victim} getting hit!")

        roll_courage = random.uniform(0, base_courage)
        roll_health = random.uniform(0, own_health)

        # If own collision group matches victim, test resolve for fleeing
        if self.character.collision_group == victim_collision:
            if roll_courage < roll_health:
                self.set_strategy("flee", 5 / self.courage)
                self.character.set_state("scared", 5 / self.courage)

        # Else, characters with Pointed weapons are prompted to charge after a flexibility check:
        else:
            if roll_courage > roll_health and self.flexibility > random.random() and isinstance(self.weapon, Pointed):
                self.set_strategy("charge", 3 - random.uniform(0, 2 * self.flexibility))

    def use_shield(self):
        """If we own a shield, hold it up"""
        offhand = self.character.slots["off_hand"]
        if isinstance(offhand, Shield):
            self.character.use("off_hand", continuous_input=(offhand.activation_offset != v()))


class Goblin(Humanoid):
    difficulty = 2

    def __init__(self, position, tier, team_color=None):
        # Modify stats according to tier
        body_stats = character_stats["body"]["goblin"]
        ai_stats = character_stats["soul"]["goblin"]
        portraits = character_stats["mind"]["goblin"]

        body_stats["health"] += 20 * (tier - 1)
        body_stats["max_speed"] += tier / 2
        ai_stats["skill"] += 0.15 * (tier - 1)

        super(Goblin, self).__init__(
            position,
            **body_stats,
            **colors['enemy'],
            faces=portraits,
            name=f"Goblin Lv.{tier:.0f}"
        )

        # Generate and equip weapon:
        self.equip(self._main_hand_goblin(tier), 'main_hand')

        # 34% of the time also generate a light Shield
        if random.random() > 0.66:

            self.equip(self._shield_goblin(tier, team_color), 'off_hand')

        self.ai = AI(self, **ai_stats)

    @staticmethod
    def _main_hand_goblin(tier):
        def goblin_blade_material():

            def filter_func(x):
                return (
                    x.name not in Material.collections["elven"] and
                    x.name not in Material.collections["mythical"]
                )

            # Mineral, 50% of the time on tier 1 and 2
            if tier <= 2 and random.random() > 0.5:
                gbm = Material.pick(["mineral"], tier, filter_func)
            # Otherwise 30% for any metal, except mythril
            elif tier <= 2 and random.random() > 0.7:
                gbm = Material.pick(["metal"], tier, filter_func)
            # Anything bone otherwise:
            else:
                gbm = Material.pick(["bone"], tier)
            return gbm

        # Goblin main hand weapon is:
        main_hand_choice = random.choices(
            ["Dagger", "Spear", "Falchion", "Sword"],
            [40, 30, 20, 10]
        )[0]

        if main_hand_choice == 'Dagger':
            # Generate dict for dagger
            dagger_builder = {
                "hilt": {
                    # Goblins make daggers themselves, so designs are simple
                    "str": random.choice(["=(", "-]"])
                },
                "blade": {
                    "str": random.choice(["==-", "≡=-", "=≡>"])
                }
            }

            dagger_builder["blade"]["material"] = goblin_blade_material()

            # Hilt material and colors would be filled in by the constructor, but we need to exclude mythril.
            if random.random() > 0.7:  # 30% of the time, pick same material for hilt
                hm = Material.pick(
                    ['metal', 'bone'],
                    tier,
                    filter_func=lambda x: (
                            x.name not in Material.collections["elven"] and
                            x.name not in Material.collections["mythical"]
                    )
                )
            else:
                hm = dagger_builder["blade"]["material"]
            dagger_builder["hilt"]["material"] = hm

            main_equipment_dict = {"constructor": dagger_builder, "tier": tier}
            main_hand_weapon = Dagger(BASE_SIZE, tier_target=tier, equipment_dict=main_equipment_dict)

        elif main_hand_choice == 'Spear':
            spear_builder = {
                "shaft": {
                    # Spears are short, light and simple, and never painted
                    "str": random.choice(["▭▭▭▭▭▭▭▭", "–-–-–-–-"])
                },
                "tip": {
                    "str": random.choice(["<>", "=-", "⊂>"])
                }
            }
            # Shaft material is always reed or very light wood
            spear_builder["shaft"]["material"] = Material.pick(
                ["wood", "reed"],
                tier,
                lambda x: (
                            x.name not in Material.collections["elven"] and
                            x.name not in Material.collections["mythical"]
                    ) and x.weight < 0.5
            )
            # Tip material has same logic as dagger material
            spear_builder["tip"]["material"] = goblin_blade_material()

            # Goblin spears are purely functional and never painted, so we generate colors now
            for part in {'shaft', 'tip'}:
                color = Material.registry[spear_builder[part]["material"]].generate()
                spear_builder[part]["color"] = color

            main_equipment_dict = {"constructor": spear_builder, "tier": tier}
            main_hand_weapon = Spear(BASE_SIZE, tier_target=tier, equipment_dict=main_equipment_dict)

        elif main_hand_choice == 'Falchion':
            falchion_builder = {
                "blade": {
                    "str": random.choice(parts_dict['falchion']['blades']),
                    "material": Material.pick(['metal'], tier, lambda x: (
                            x.name not in Material.collections["elven"] and
                            x.name not in Material.collections["mythical"]
                    ))
                },
                "hilt": {}
            }

            if random.random() > 0.6:  # 40% of the time, pick same material for hilt
                falchion_builder['hilt']['material'] = Material.pick(
                    ['metal', 'bone', 'precious', 'wood'],
                    tier,
                    lambda x: (
                            x.name not in Material.collections["elven"] and
                            x.name not in Material.collections["mythical"]
                    )
                )
            else:
                falchion_builder['hilt']['material'] = falchion_builder["blade"]["material"]

            main_equipment_dict = {"constructor": falchion_builder, "tier": tier}
            main_hand_weapon = Falchion(BASE_SIZE, tier_target=tier, equipment_dict=main_equipment_dict)

        # Random short Sword rest of the time
        else:
            # Swords are scavenged, goblins don't make swords
            # Only requirement is to be short and never contain elven materials
            def make_blade(blade_parts):
                return blade_parts[0] * 3 + blade_parts[1]

            blade_string = make_blade(random.choice(parts_dict['sword']['blades']))

            sword_builder = {
                "blade": {
                    "str": blade_string,
                    "material": Material.pick(['metal'], tier, lambda x: x.name not in Material.collections["elven"])
                },
                "hilt": {}
            }
            if random.random() > 0.6:  # 40% of the time, pick same material for hilt
                sword_builder['hilt']['material'] = Material.pick(
                    ['metal', 'bone', 'precious', 'wood'],
                    tier,
                    lambda x: x.name not in Material.collections["elven"]
                )
            else:
                sword_builder['hilt']['material'] = sword_builder["blade"]["material"]

            main_equipment_dict = {"constructor": sword_builder, "tier": tier}
            main_hand_weapon = Sword(BASE_SIZE, tier_target=tier, equipment_dict=main_equipment_dict)

        return main_hand_weapon

    @staticmethod
    def _shield_goblin(tier, team_color):
        shield_builder = {"frame": {
            "material": Material.pick(["reed"], tier)
        }, "plate": {
            "material": Material.pick(
                ['metal', 'wood', 'leather', 'bone'],
                tier,
                lambda x: (
                        x.name not in Material.collections['plateless_bone'] and
                        x.name not in Material.collections['elven'] and
                        x.name not in Material.collections['mythical'] and
                        x.weight <= 0.5
                )
            )
        }}

        # If specified, paint plate team color; otherwise let .generate handle it
        if team_color and Material.registry[shield_builder['plate']['material']].physics in PAINTABLE:
            shield_builder['plate']['color'] = team_color
            shield_builder['plate']['tags'] = ['painted']

        off_equipment_dict = {"constructor": shield_builder, "tier": tier}
        return Shield(BASE_SIZE, tier_target=tier, equipment_dict=off_equipment_dict)


class Human(Humanoid):
    difficulty = 3

    def __init__(self, position, tier):
        # Modify stats according to tier
        body_stats = character_stats["body"]["human"]
        ai_stats = character_stats["soul"]["human"]
        portraits = character_stats["mind"]["human"]

        body_stats["health"] += 20 * (tier - 1)
        body_stats["max_speed"] += tier / 2
        ai_stats["skill"] += -0.5 + tier / 2

        super().__init__(position, **body_stats, **colors['enemy'], faces=portraits)


class Orc(Humanoid):
    difficulty = 3.5

    def __init__(self, position, tier, team_color=None):
        # Modify stats according to tier
        body_stats = character_stats["body"]["orc"]
        ai_stats = character_stats["soul"]["orc"]
        portraits = character_stats["mind"]["orc"]

        body_stats["health"] += 40 * (tier - 1)
        body_stats["max_speed"] += tier / 3
        ai_stats["skill"] += 0.1 * (tier - 1)

        super().__init__(
            position,
            **body_stats,
            **colors['enemy'],
            faces=portraits,
            name=f"Orc Lv.{tier:.0f}"
        )

        self.equip(Sword(BASE_SIZE, tier_target=tier), 'main_hand')
        self.equip(Shield(BASE_SIZE, tier_target=tier), 'off_hand')

        self.ai = AI(self, **ai_stats)


class DebugGoblin(Goblin):

    def __init__(self, *args, **kwargs):
        super(DebugGoblin, self).__init__(*args, **kwargs)
        self.max_speed = 0

    def move(self, *args, **kwargs):
        super(DebugGoblin, self).move(*args, **kwargs)
        self.position = v(SCENE_BOUNDS.center)
