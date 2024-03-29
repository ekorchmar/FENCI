# todo:
# After tech demo
# todo:
#  ?? animate character flip
#  ?? Treasure goblins
#  off-hand weapons for goblins and humans
#  Animal(Character) subclass
#   Monsters: Goblin, Wolf, Rat, Elf, Orc, Demon
#  generate equipment for Elf
#  AI can use off-hand weapons, not just shields
# todo: celebration state if away from enemy and flexibility >> skill or all enemies dead
# todo: randomly exchange wait <=> to wander: move to a new position, not too close to arena edge

import base_class as b
import particle as pt
import equipment as eq
from primitive import *
from typing import Any


class Humanoid(b.Character):
    skirmish_spawn_rate = 0
    weapon_slots = ["main_hand", "off_hand"]
    body_coordinates = {
        "face": [0, 0],
        "main_hand": [-40, 25],
        "off_hand": [50, 25],
        "hat": [15, -30],
        "bars": [0, -45]
    }

    def __init__(self, position, size, hand, *args, blink=5, **kwargs):
        super().__init__(position, size, *args, **kwargs)
        self.slots: dict[str, Any] = {
            "main_hand": b.Nothing(),
            "off_hand": b.Nothing(),
            "hat": b.Nothing(),
            "backpack": b.Nothing()
        }
        self.body_coordinates = Humanoid.body_coordinates.copy()
        scale_body(self.body_coordinates, size)

        # Randomize blink
        self.blink = blink
        self.blink_timer = self.blink * random.gauss(1.0, 0.1)

        # Add hands
        self.hand = pygame.transform.rotate(ascii_draw(self.size, hand, self.color), -180)
        self.hand_rect = self.hand.get_rect()

        # Place to store values for weapon-specific bars
        self.main_hand = None
        self.off_hand = None
        self.hat = None
        self.weapon_bar_options = {
            'size': BASE_SIZE // 3,
            'width': 10,
            'base_color': colors["bar_base"],
            'show_number': False
        }

    def do_blink(self):
        # Randomize next blink:
        self.blink_timer = self.blink * random.gauss(1.0, 0.1)

        self.state = random.choice(['blink', 'blink', 'idle_rare'])
        if self.state == 'idle_rare':
            self.state_timer = self.all_faces[self.size][self.state][-1]
        else:
            self.state_timer = 0.1

    def draw(self, body_only=False, freeze=False, **kwargs):
        return_list = super().draw(body_only=body_only, **kwargs)

        if self.state_timer < -self.blink_timer and self.state == 'idle':
            self.do_blink()

        # Modify placement by adding placement coordinates and relative offset from self.body_coordinates
        # 1. Draw face

        # Pick facial expression (defaults to idle)
        face_row = self.all_faces[self.size].get(self.visual_state, self.all_faces[self.size]['idle'])
        if face_row[-1] > 0:
            # Find in which phase of anumation are we
            faces, duration = face_row[:-1], face_row[-1]
            time_per_frame = duration / len(faces)  # total time / faces number
            index = int(self.visual_timer / time_per_frame)
            face_pick = faces[index % len(faces)]
        else:
            face_pick = face_row[0]

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

        oscillation_y = 0 if freeze else -self.size * math.sin(self.life_timer * 2) * 0.15
        modified_center.y += oscillation_y
        face_rect = face_pick.get_rect(center=modified_center)

        # If skewered on a weapon, tilt slightly towards the weapon:
        if self.anchor_weapon and self.anchor_timer > 0:
            if 90 >= self.anchor_weapon.last_angle > 0:
                tilt_angle = -15
            elif 90 < self.anchor_weapon.last_angle:
                tilt_angle = 15
            elif -90 <= self.anchor_weapon.last_angle:
                tilt_angle = 15
            else:
                tilt_angle = -15

            face_pick = pygame.transform.rotate(face_pick, tilt_angle)

        if self.immune_timer > 0:
            transparent_face = face_pick.copy()
            transparency = int(127 + 127 * math.sin(pygame.time.get_ticks() * 0.02))
            transparent_face.set_alpha(transparency)
            return_list.append((transparent_face, face_rect))
        else:
            return_list.append((face_pick, face_rect))

        # 2. Draw hat, if available
        if self.slots["hat"]:
            hat_center = self.position + v(self.body_coordinates['hat'])
            hat_center.y += oscillation_y
            output = self.slots["hat"].draw(self, hat_center)
            return_list.append(output)
            self.drawn_equipment[self.slots["hat"]] = output[1]

        # 3. Draw equipped aimed off-hand and main weapons
        for weapon in self.weapon_slots:

            if not body_only:

                # Draw hand first if hides_hand is True:
                if self.slots[weapon].hides_hand:
                    surface, rect = self._draw_hand(weapon)
                    surface_copy = surface.copy()
                    surface_copy.set_alpha(100)
                    return_list.append((surface_copy, rect))

                if not self.slots[weapon]:
                    # Draw hand and skip
                    return_list.append(self._draw_hand(weapon))
                    continue

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

                # Draw hand, if not hides hand
                if not self.slots[weapon].hides_hand:
                    return_list.append(self._draw_hand(weapon))

        return return_list

    def _draw_hand(self, slot):
        if not self.slots[slot] or not self.slots[slot].hilt_v:
            hand_location = v(self.position) + v(self.body_coordinates[slot])
        else:
            hand_location = v(self.slots[slot].hilt_v)

        hand_angle = self.slots[slot].last_angle + self.slots[slot].hand_rotation

        hand_surface, hand_rect = rot_center(self.hand, hand_angle, hand_location)
        # I'm not sure hitbox should include hands. Creates a lot of accidental pushing.
        # self.hitbox.append(hand_rect)
        return [hand_surface, hand_rect]

    def backpack_swap(self, scene):
        backpack = self.slots["backpack"]
        if not backpack:
            return

        slot = backpack.prefer_slot

        self.slots["backpack"], self.slots[slot] = self.slots[slot], self.slots["backpack"]
        self.slots[slot].reset(self, True)

        # Inform the scene:
        scene.log_weapons()

    def update(self, target=None, disable_weapon=False):
        super(Humanoid, self).update(target, disable_weapon)

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
                self.bars["roll_cooldown"] = b.Bar(
                    BASE_SIZE // 3,
                    10,
                    colors["bar_base"],
                    self.roll_cooldown,
                    base_color=colors["bar_base"],
                    show_number=False
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

    @staticmethod
    def get_main(tier, size=BASE_SIZE) -> eq.Wielded:
        # Equal chance for any main hand weapon:
        main_class = random.choice([cls for cls in eq.Wielded.registry.values() if cls.prefer_slot == 'main_hand'])
        return main_class(tier_target=tier, size=int(size))

    @staticmethod
    def get_shield(tier, size=BASE_SIZE, team_color=None) -> eq.Shield:
        shield = eq.Shield(tier_target=tier, size=size)
        # Force team color, if plate is painted:
        if (
                team_color and
                'tags' in shield.builder['constructor']['plate'] and
                'painted' in shield.builder['constructor']['plate']['tags']
        ):
            shield.builder['constructor']['plate']['color'] = team_color
            shield.generate()
            shield.update_stats()

        return shield


# AI classes
class AI:
    _base_aggression = 2

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
        self.perceived_health = 0
        self.morale = 1.0
        self.speed_limit = 1.0

        # Own equipment assessments:

        # These constants are not subject to be randomized by skill function, as they are base
        self.tick_stamina_consumption = self.weapon.stamina_drain * 250 * FPS_TICK
        self.angular_acceleration = self.character.agility * self.weapon.agility_modifier * FPS_TICK * 6.7

        # Stab attack of Pointed weapon
        self.stab_reach_rx, self.stab_reach_ry = 0, 0
        self.stab_stamina_cost = 0

        # Swing attack is trickier
        self.swing_range = 0  # Max range(a.k.a. weapon length)
        self.swing_stamina_cost = 0  # What is stamina cost of accelerating weapon to SWING_TRESHOLD
        self.swing_windup_time = 0  # How long weapon must be moving from standstill to reach SWING_TRESHOLD
        self.swing_windup_angle = 0  # What is minimal angle windup is required to start swinging from standstill

        # eq.Falchion roll
        self.roll_range = 0

        # eq.Axe whirlwind
        self.whirlwind_charge_time = 0  # Duration required for 3 spins
        self.whirlwind_cost = 0  # Cost to start whirlwinding
        self.whirlwing_charge_range = 0  # Distance required for full charge power-up

        # Initial calculations:
        self.calculate_stab()
        self.calculate_swing()
        self.calculate_roll()
        self.calculate_whirlwind()

        # Introduce standard mistake: will be re-rolled each analysis
        self.error = self._skill_distribution()

    def roll_error(self):
        self.error = self._skill_distribution()

    def _skill_distribution(self, value=1.0):
        return value * random.gauss(1.0, 0.05 - self.skill * 0.2)

    def warn(self):
        warning_position = self.character.body_coordinates["bars"] + v(0, -2*BASE_SIZE)
        warning_particle = pt.AttackWarning(warning_position, self.character, self.attack_delay)
        self.scene.particles.append(warning_particle)
        return warning_particle

    def set_strategy(self, strategy, follow_time):
        self.strategy = strategy
        self.strategy_timer = follow_time

        # Remove all own warnings from scene particles:
        for key in filter(lambda x: isinstance(self.strategy_dict[x], pt.AttackWarning), self.strategy_dict):
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
        if not isinstance(self.weapon, eq.Pointed) or isinstance(self.weapon, (eq.Falchion, eq.Mace)):
            return

        # Calculate own max stab reach distance when equipping Pointed weapon
        max_speed_component = 0.2 * self.character.max_speed * FPS_TARGET

        stab_modifier = 2.5 * FPS_TICK * BASE_SIZE * self.character.agility * \
            self.weapon.stab_modifier * self.weapon.agility_modifier

        self.stab_reach_rx = self.weapon.length + 2 * max_speed_component + stab_modifier
        self.stab_reach_ry = self.weapon.length + 1.2 * max_speed_component + stab_modifier
        self.stab_stamina_cost = self.character.max_stamina * self.weapon.stab_cost

    def calculate_roll(self):
        if not isinstance(self.weapon, eq.Falchion):
            return

        self.roll_range = 0.5 * self.weapon.character_specific["roll_treshold"] * FPS_TARGET

    def calculate_swing(self):
        if not isinstance(self.weapon, eq.Bladed):
            return

        self.swing_range = self.weapon.length
        self.swing_windup_time = SWING_THRESHOLD * FPS_TICK / self.angular_acceleration
        self.swing_stamina_cost = self.swing_windup_time * (FPS_TARGET * self.tick_stamina_consumption)
        self.swing_windup_angle = 0.5 * FPS_TARGET * self.angular_acceleration * (self.swing_windup_time ** 2)

    def calculate_whirlwind(self):
        if not isinstance(self.weapon, eq.Axe):
            return

        # Duration required for 3 spins
        self.whirlwind_charge_time = self.weapon.full_charge_time
        # Cost to start whirlwinding
        self.whirlwind_cost = self.character.max_stamina * 0.5
        # Range to charge up in time:
        self.whirlwing_charge_range = 0.75*self.whirlwind_charge_time * self.character.max_speed * FPS_TARGET + \
            2*self.swing_range

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

        self._assess(scene)
        # Default AI has 5% chance to fall to Rhino factor
        if self.target and 0.1 * self.aggression * self.courage > random.uniform(0, self.flexibility):
            self.set_strategy("charge", 12)
            self.strategy_dict["FULL RHINO"] = True

        self._decide(initial)

    def _decide(self, initial):
        # No enemies? We wait.
        if not self.enemies:
            self.set_strategy('wait', 3 - random.uniform(0, 2 * self.flexibility))
            return

        # Assess effective distance to target:
        desired_sparring_distance = self.whirlwing_charge_range or max(
            self.effective_range(),
            self.enemies[self.target]["reach"]
        ) * 1.2

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
                friend.ai.target is self.target,
                self.friends[friend]["health"] >= self.courage,
                self.friends[friend]["distance"] <= self.enemies[self.target]["distance"] * 1.5
            ]):
                count_allies += 1

        # Test if we have a next plan:
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
            # elif isinstance(self.target.shielded, Shield) and \
            #         random.uniform(0, self.aggression) < random.uniform(0, self.skill) * 0.5:
            #     violence = False

            # Test if target "looks" healthier than we are, possibly chicken out
            elif self.perceived_health / self.enemies[self.target]["health"] < random.uniform(0, self.courage):
                violence = False

            # Decide if we enter aggressive state, based on game state. If decision is negative, repeat
            # decision process for every ally, until positive conclusion is reached, or if we ran out of allies:
            else:
                violence = False
                agression_chance = self.aggression * self.morale * self.character.stamina / self.character.max_stamina
                for _ in range(self._base_aggression + count_allies + 1):
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
            if not isinstance(self.weapon, eq.Bladed):
                violence = False

            # Test if we have enough stamina for swing attack:
            elif self.swing_stamina_cost and self.character.stamina < self.swing_stamina_cost:
                violence = False

            # Test if target is shielded and self is not too eager:
            # elif isinstance(self.target.shielded, Shield) and \
            #         random.uniform(0, self.aggression) > random.uniform(0, self.skill):
            #     violence = False

            # Test if we are behind the target that faces same way:
            elif (
                    self.character.facing_right ==
                    self.target.facing_right ==
                    (self.character.position.x < self.target.position.x)
            ):
                violence = True

            # Now test if enemy weapon is not suited for CQC while our is; needs flexibility check:
            elif not isinstance(self.enemies[self.target]["weapon"], eq.Bladed) and \
                    isinstance(self.weapon, eq.Bladed) and \
                    self.flexibility > random.random():
                violence = True

            # Test if target "looks" healthier than we are, possibly chicken out
            elif self.perceived_health / self.enemies[self.target]["health"] < random.uniform(0, self.courage):
                violence = False

            # Decide if we enter aggressive state, based on game state. If decision is negative, repeat
            # decision process for every ally, until positive conclusion is reached, or if we ran out of allies:
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

    def _assess(self, scene):
        # General situation awareness:
        self.scene = scene
        self.enemies = {}
        self.friends = {}
        self.perceived_health = min(
            self.character.hp / self.character.max_hp,
            self.character.stamina / self.character.max_stamina
        )

        # Drop dead targets:
        if self.target and self.target.hp <= 0:
            self.target = None

        # Count enemies, assess their health and assume their weapon reach:
        enemies_list = list(
            filter(lambda x: x.collision_group != self.character.collision_group, self.scene.characters)
        )
        # Put target first so that distance to it is assessed first
        enemies_list.sort(key=lambda x: x is not self.target)
        for enemy in enemies_list:
            # Ignore enemies with no hitbox:
            if not enemy.hitbox:
                continue

            weapon_slot = enemy.weapon_slots[0]
            enemy_weapon = enemy.slots[weapon_slot]

            if not enemy_weapon:
                reach = 0
            elif isinstance(enemy_weapon, (eq.Spear, eq.Sword, eq.Dagger)):
                reach = enemy_weapon.length * 1.2 + v(enemy.body_coordinates[weapon_slot]).length()
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
            if (self.target is None or distance < self.enemies[self.target]["distance"]) and enemy.hp > 0:
                self.target = enemy

        # Count friends and assess their state:
        for friend in filter(
                lambda x: x is not self.character and x.collision_group == self.character.collision_group,
                self.scene.characters
        ):
            weapon_slot = friend.weapon_slots[0]
            weapon = friend.slots[weapon_slot]
            if isinstance(weapon, eq.Pointed):
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
        distances = dict()
        for body in filter(lambda x: x is not self.character, self.scene.characters):
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

            # Shields may disable weapons:
            if isinstance(self.character.slots["off_hand"], eq.Shield):
                parry = self.weapon.disabled and not any((
                    self.character.slots["off_hand"].active_last_frame,
                    self.character.slots["off_hand"].active_this_frame
                ))
            # eq.Axes may be locked by charging up:
            elif isinstance(self.weapon, eq.Axe):
                parry = self.weapon.disabled and not self.weapon.locked_from_activation
            # Parried? Switch to confront
            else:
                parry = self.weapon.disabled

            if parry:
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

            # For anything stabby
            if isinstance(self.weapon, eq.Pointed) and self.stab_stamina_cost > 0:
                self.strategy_dict["plan"] = "stab"
                # If stab is already planned, check warning time lifetime:
                if "warning" in self.strategy_dict:
                    # If warning time ran out:
                    if self.strategy_dict["warning"].lifetime <= 0 and self.character.stamina > self.stab_stamina_cost:
                        # Execute stab:
                        self.character.use(self.slot, continuous_input=False)
                        self.strategy_dict.pop("warning")
                        # Fix follow time, to guarantee reassessment after the stab is over, even if it misses
                        self.strategy_timer = self.weapon.stab_duration

                elif self.character.stamina > self.stab_stamina_cost and self.in_stab_range():
                    # Spawn warning and use its lifetime as counter before the attack
                    self.strategy_dict["warning"] = self.warn()
                    self.strategy_dict["timestamp"] = pygame.time.get_ticks()

                # Otherwise, clear own intent to attack
                else:
                    self.set_strategy('charge', max(self.strategy_timer, 0))

            # For eq.Falchions, roll in:
            elif self.roll_range > 0:
                self.strategy_dict["plan"] = "roll in"
                # ?? Todo: high skill may attempt to purposefully roll through the player
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

            # For eq.Axes, spin up before running up to character
            elif self.whirlwind_cost > 0:
                # If we are already calculated end of the spin, pass
                if "stop_thinking" in self.strategy_dict:
                    pass
                # If we have started spinning, querry an analysis
                elif self.weapon.spin_remaining > 0:
                    spin_time = FPS_TICK * self.weapon.spin_remaining / abs(self.weapon.angular_speed)
                    self.strategy_timer = spin_time
                    self.strategy_dict["stop_thinking"] = None
                # If an attack warning is already here:
                elif "warning" in self.strategy_dict:
                    # If active, keep powering up:
                    if self.strategy_dict["warning"].lifetime > 0:
                        self.character.use(self.slot, continuous_input=True)
                    else:
                        # Release, spin will follow
                        pass
                # If weapon is already being charged:
                elif self.weapon.locked_from_activation:
                    # Slow down, keep charging
                    self.speed_limit = 0.75
                    self.character.use(self.slot, continuous_input=True)
                    # Spawn attack warning once charge is complete or if we are 2 reaches away:
                    if self.weapon.charge_time >= self.weapon.full_charge_time or \
                            distances[self.target] <= self.swing_range * 2:
                        self.strategy_dict["warning"] = self.warn()
                        self.strategy_dict["timestamp"] = pygame.time.get_ticks()
                # If we are too close to enemy to attempt charge, switch to dogfight
                elif distances[self.target] <= self.swing_range * 1.2:
                    self.strategy_dict["next"] = ('dogfight', 5 - random.uniform(0, 2 * self.flexibility))
                    self.analyze(self.scene)
                # Finally, assess if enemy is in full charge distance, and start channeling spin if yes:
                elif distances[self.target] <= self.whirlwing_charge_range and \
                        self.character.stamina > self.whirlwind_cost:
                    self.character.use(self.slot, continuous_input=True)

            # For Maces and other generic Bladed, run in; have a chance to switch for dogfight
            elif isinstance(self.weapon, eq.Bladed):
                # If we are close, switch to dogfight:
                if distances[self.target] <= 1.2 * self.swing_range:
                    # Immediately switch to dogfight
                    self.strategy_dict["next"] = ('dogfight', 5 - random.uniform(0, 2 * self.flexibility))
                    self.analyze(self.scene)

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
            # If we ran out of stamina, stop and wait:
            if self.character.stamina < self.character.max_stamina * 0.1:
                self.character.set_state('exhausted', 1)
                self.strategy_dict["next"] = 'wait', 3+random.uniform(0, 1-self.flexibility)
                self.analyze(self.scene)
                return self.execute()

            if self.target is None or self.target.hp <= 0:
                self.analyze(self.scene)
                return self.execute()

            self.speed_limit = 0.25 + 0.75 * self.courage
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
                # Character may stay outside own reach if enemy reach is longer
                # corridor is 0.8a < d < 1.2a
                desired_distance = max(self.effective_range(), self.enemies[self.target]["reach"], 1)
                actual_distance = distances[self.target]
                if 0.8*actual_distance < desired_distance < 1.2*actual_distance:
                    # Roll for aggression, either prepare to charge or keep circling around target
                    agression_chance = self.aggression * self.morale * self.character.stamina /\
                        self.character.max_stamina
                    if random.random() < agression_chance:  # and not isinstance(self.target.shielded, Shield):
                        self.strategy_dict["plan"] = "prepare"
                        substrategy = "prepare"
                        self.strategy_dict["timer"] = self.flexibility  # Keep attacks more or less predictable
                        self.strategy_dict["next"] = ("charge", 5)
                    else:
                        self.strategy_dict["plan"] = "circle"
                        substrategy = "circle"
                        self.strategy_dict["radius"] = distances[self.target]
                        self.strategy_dict["timer"] = 2 + random.uniform(0, self.flexibility)
                        # Find the closest ally; pick clockwise/ccw direction to move AWAY from ally
                        try:
                            closest_friend = sorted(self.friends.keys(), key=lambda x: self.friends[x]["distance"])[0]
                            ccw = ccw_triangle(
                                self.target.position,
                                self.character.position,
                                closest_friend.position
                            )
                            # Move in OPPOSITE direction:
                            self.strategy_dict["ccw"] = ccw
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

                if self.target not in distances:
                    self.analyze(self.scene)

                # If we are in range, clear subplan for the future:
                if 0.8 * distances[self.target] < self.strategy_dict["desired_distance"] < 1.2 * distances[self.target]:
                    self.strategy_dict = {}

                # Limit speed if we are around desired distance:
                elif "desired_distance" in self.strategy_dict:
                    relative_deviation = (
                        distances[self.target] / self.strategy_dict["desired_distance"]
                        if distances[self.target] < self.strategy_dict["desired_distance"]
                        else self.strategy_dict["desired_distance"] / distances[self.target]
                    )
                    self.speed_limit = lerp((0.25, self.speed_limit), 1-relative_deviation)

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
                    target_distance < 2.25*self.weapon.length*self.weapon.length:
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

                    if body is self.target and \
                            not (self.strategy == 'dogfight' and self.strategy_dict["stage"] == "hit"):
                        # Consider fleeing, then consider aggression
                        self.fight_or_flight(victim=self.character)
                        self.fight_or_flight(victim=self.target)

        return directions

    def fight_or_flight(self, victim):
        """
        Takes an object in scene, either a hurt character or a parried weapon. Reaction can be either to charge in,
        start fleeing, querry up a state change, or analyze situation anew
        """
        # Can't activate FOF too often:
        if self.fof_time < self.flexibility * 5:
            return

        # If we are busy, ignore
        if self.strategy in BUSY:
            return

        # If victim is target, and it's dead, switch to waiting:
        if victim is self.target and victim.hp <= 0:
            self.set_strategy("wait", 6 - random.uniform(0, 2 * self.flexibility))
            return

        # Reset timer for next FOF reaction
        self.fof_time = 0

        base_courage = self.courage * self.morale
        self.perceived_health = min(
            self.character.hp / self.character.max_hp,
            self.character.stamina / self.character.max_stamina
        )

        if isinstance(victim, b.Character):
            # Less courage if we are hit
            if victim is self.character:
                base_courage *= self.courage
            else:
                # Far away is less impactful
                distance_mod = self.scene.box.width * self.scene.box.height / \
                    (v(self.character.position) - v(victim.position)).length_squared()
                base_courage *= distance_mod

            # More courage if target is hit
            if victim is self.target:
                base_courage += (1-base_courage) * 2

            victim_collision = victim.collision_group

        elif isinstance(victim, b.Equipment):
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
        roll_health = random.uniform(0, self.perceived_health)

        # If own collision group matches victim, test resolve for fleeing
        if self.character.collision_group == victim_collision:

            # If characters size is more than targets size, flee only if morale is below (1-own courage):
            if self.target and self.target.size < self.character.size and self.morale > (1-self.courage):
                return

            if roll_courage < roll_health and len(self.friends) < 2:
                self.set_strategy("flee", 5 / self.courage)
                self.character.set_state("scared", 5 / self.courage)

        # Else, characters are prompted to charge after a flexibility check:
        else:
            if roll_courage > roll_health and self.flexibility > random.random():
                self.set_strategy("charge", 3 - random.uniform(0, 2 * self.flexibility))

    def use_shield(self):
        """If we own a shield, hold it up"""
        offhand = self.character.slots["off_hand"]
        if isinstance(offhand, eq.Shield):
            self.character.use("off_hand", continuous_input=(offhand.activation_offset != v()))


class DebugAI(AI):
    def __init__(self, character):
        super(DebugAI, self).__init__(character)

    def _decide(self, initial):
        self.set_strategy('wait', 100)

    def _assess(self, scene):
        self.scene = scene
        pass

    def execute(self):
        if self.character.state in DISABLED and not self.character.anchor_timer > 0:
            self.character.speed *= 0.5
        return v(), None


# Monster classes
class Goblin(Humanoid):
    skirmish_spawn_rate = 5
    class_name = "Goblin"
    difficulty = 2
    knockback_resistance = 0.1

    def __init__(self, position, tier, team_color=None):
        # Modify stats according to tier
        body_stats = character_stats["body"]["Goblin"].copy()
        ai_stats = character_stats["soul"]["Goblin"].copy()
        portraits = character_stats["mind"]["Goblin"].copy()

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
        self.equip(self.get_main(tier), 'main_hand')

        # 34% of the time also generate a light Shield
        if random.random() > 0.66:
            self.equip(self.get_shield(tier=tier, team_color=team_color), 'off_hand')

        self.ai = AI(self, **ai_stats)

    @staticmethod
    def get_main(tier, size=BASE_SIZE) -> eq.Wielded:

        def goblin_blade_material():
            def filter_func(x):
                return (
                    x.name not in b.Material.collections["elven"] and
                    x.name not in b.Material.collections["mythical"]
                )

            # Mineral, 50% of the time on tier 1 and 2
            if tier <= 2 and random.random() > 0.5:
                gbm = b.Material.pick(["mineral"], tier, filter_func)
            # Otherwise, 30% for any metal, except mythril
            elif tier <= 2 and random.random() > 0.7:
                gbm = b.Material.pick(["metal"], tier, filter_func)
            # Anything bone otherwise:
            else:
                gbm = b.Material.pick(["bone"], tier, filter_func)
            return gbm

        # Goblin main hand weapon is:
        main_hand_choice = random.choices(
            ["Dagger", "Spear", "Falchion", "Sword"],
            [40, 30, 20, 10]
        )[0]

        if main_hand_choice == 'Dagger':
            # Generate dict for eq.Dagger
            dagger_builder = {
                "hilt": {
                    # Goblins make eq.Daggers themselves, so designs are simple
                    "str": random.choice(["=(", "-]"])
                },
                "blade": {
                    "str": random.choice(["==-", "≡=-", "=≡>"])
                }
            }

            dagger_builder["blade"]["material"] = goblin_blade_material()

            # Hilt material and colors would be filled in by the constructor, but we need to exclude mythril.
            if random.random() > 0.7:  # 30% of the time, pick same material for hilt
                hm = b.Material.pick(
                    ['metal', 'bone'],
                    tier,
                    filter_func=lambda x: (
                            x.name not in b.Material.collections["elven"] and
                            x.name not in b.Material.collections["mythical"]
                    )
                )
            else:
                hm = dagger_builder["blade"]["material"]
            dagger_builder["hilt"]["material"] = hm

            main_equipment_dict = {"constructor": dagger_builder, "tier": tier}
            main_hand_weapon = eq.Dagger(size, tier_target=tier, equipment_dict=main_equipment_dict)

        elif main_hand_choice == 'Spear':
            spear_builder = {
                "shaft": {
                    # eq.Spears are short, light and simple, and never painted
                    "str": random.choice(["▭▭▭▭▭▭▭▭", "–-–-–-–-"])
                },
                "head": {
                    "str": random.choice(["<>", "═-", "⊂>"])
                }
            }
            # Shaft material is always reed or very light wood
            spear_builder["shaft"]["material"] = b.Material.pick(
                ["wood", "reed"],
                tier,
                lambda x: (
                            x.name not in b.Material.collections["elven"] and
                            x.name not in b.Material.collections["mythical"]
                    ) and x.weight < 0.5
            )
            # Tip material has same logic as eq.Dagger material
            spear_builder["head"]["material"] = goblin_blade_material()

            # Goblin eq.Spears are purely functional and never painted, so we generate colors now
            for part in {'shaft', 'head'}:
                color = b.Material.registry[spear_builder[part]["material"]].generate()
                spear_builder[part]["color"] = color

            main_equipment_dict = {"constructor": spear_builder, "tier": tier}
            main_hand_weapon = eq.Spear(size, tier_target=tier, equipment_dict=main_equipment_dict)

        elif main_hand_choice == 'Falchion':
            falchion_builder = {
                "blade": {
                    "str": random.choice(parts_dict['falchion']['blades']),
                    "material": b.Material.pick(['metal'], tier, lambda x: (
                            x.name not in b.Material.collections["elven"] and
                            x.name not in b.Material.collections["mythical"]
                    ))
                },
                "hilt": {}
            }

            if random.random() > 0.6:  # 40% of the time, pick same material for hilt
                falchion_builder['hilt']['material'] = b.Material.pick(
                    ['metal', 'bone', 'precious', 'wood'],
                    tier,
                    lambda x: (
                            x.name not in b.Material.collections["elven"] and
                            x.name not in b.Material.collections["mythical"]
                    )
                )
            else:
                falchion_builder['hilt']['material'] = falchion_builder["blade"]["material"]

            main_equipment_dict = {"constructor": falchion_builder, "tier": tier}
            main_hand_weapon = eq.Falchion(size, tier_target=tier, equipment_dict=main_equipment_dict)

        # Random short Sword rest of the time
        else:
            # eq.Swords are scavenged, goblins don't make eq.Swords
            # Only requirement is to be short and never contain elven materials
            def make_blade(blade_parts):
                return blade_parts[0] * 3 + blade_parts[1]

            blade_string = make_blade(random.choice(parts_dict['sword']['blades']))

            sword_builder = {
                "blade": {
                    "str": blade_string,
                    "material": b.Material.pick(
                        ['metal'], tier, lambda x: x.name not in b.Material.collections["elven"]
                    )
                },
                "hilt": {}
            }
            if random.random() > 0.6:  # 40% of the time, pick same material for hilt
                sword_builder['hilt']['material'] = b.Material.pick(
                    ['metal', 'bone', 'precious', 'wood'],
                    tier,
                    lambda x:
                        x.name not in b.Material.collections["elven"] and
                        x.name not in b.Material.collections["mythical"]
                )
            else:
                sword_builder['hilt']['material'] = sword_builder["blade"]["material"]

            main_equipment_dict = {"constructor": sword_builder, "tier": tier}
            main_hand_weapon = eq.Sword(size, tier_target=tier, equipment_dict=main_equipment_dict)

        return main_hand_weapon

    @staticmethod
    def get_shield(tier, size=BASE_SIZE, team_color=None):
        shield_builder = {"frame": {
            "material": b.Material.pick(["reed"], tier)
        }, "plate": {
            "material": b.Material.pick(
                ['metal', 'wood', 'leather', 'bone'],
                tier,
                lambda x: (
                        x.name not in b.Material.collections['plateless_bone'] and
                        x.name not in b.Material.collections['elven'] and
                        x.name not in b.Material.collections['mythical'] and
                        x.weight <= 0.5
                )
            )
        }}

        # If specified, paint plate team color; otherwise let .generate handle it
        if team_color and b.Material.registry[shield_builder['plate']['material']].physics in PAINTABLE:
            shield_builder['plate']['color'] = team_color
            shield_builder['plate']['tags'] = ['painted']

        off_equipment_dict = {"constructor": shield_builder, "tier": tier}
        return eq.Shield(size, tier_target=tier, equipment_dict=off_equipment_dict)


class Human(Humanoid):
    skirmish_spawn_rate = 2
    class_name = "Human"
    difficulty = 3
    knockback_resistance = 0.5

    def __init__(self, position, tier, team_color=None):
        # Modify stats according to tier
        body_stats = character_stats["body"]["Human"].copy()
        ai_stats = character_stats["soul"]["Human"].copy()
        portraits = character_stats["mind"]["Human"].copy()

        body_stats["health"] += 20 * (tier - 1)
        body_stats["max_speed"] += tier / 2
        ai_stats["skill"] += -0.5 + tier / 2

        super().__init__(
            position,
            **body_stats,
            **colors['enemy'],
            faces=portraits,
            name=f"Human Lv.{tier:.0f}"
        )

        # Humans use anything, so allow random generation:
        self.equip(self.get_main(tier), 'main_hand')
        # Shield in 50% cases
        if random.random() > 0.5:
            shield = self.get_shield(tier, self.size, team_color)
            self.equip(shield, 'off_hand')

        # Add AI:
        self.ai = AI(self, **ai_stats)


class Orc(Humanoid):
    skirmish_spawn_rate = 1
    class_name = 'Orc'
    difficulty = 3.5
    knockback_resistance = 0.65

    def __init__(self, position, tier, team_color=None):
        # Modify stats according to tier
        body_stats = character_stats["body"]["Orc"].copy()
        ai_stats = character_stats["soul"]["Orc"].copy()
        portraits = character_stats["mind"]["Orc"].copy()

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

        self.equip(self.get_main(tier, size=self.size), 'main_hand')
        # 80% of the time also generate a heavy Shield
        if random.random() > 0.2:
            self.equip(self.get_shield(tier=tier, team_color=team_color, size=self.size), 'off_hand')

        self.ai = AI(self, **ai_stats)

    @staticmethod
    def get_main(tier, size=BASE_SIZE):

        # Don't use Elven, never use light materials
        def filter_func(x):
            return (
                    x.name not in b.Material.collections["elven"] and
                    x.name not in b.Material.collections["celestial"] and
                    x.weight >= 0.8
            )

        def orc_blade_material():
            # Mineral, 50% of the time on tier 1 and 2
            if tier <= 2 and random.random() > 0.5:
                gbm = b.Material.pick(["mineral"], tier, filter_func)
            # Otherwise, any metal
            else:
                gbm = b.Material.pick(["metal"], tier, filter_func)
            return gbm

        # Goblin main hand weapon is:
        main_hand_choice = random.choices(
            ["Axe", "Sword", "Spear"], [65, 25, 10]
        )[0]

        if main_hand_choice == 'Axe':
            # Generate dict for eq.Axe
            axe_builder = {"head": {"material": orc_blade_material()}}

            # Handle material and colors would be filled in by the constructor, but we need to exclude elven.

            def new_handle_material():
                # 20% of the time, pick same metal for METALLIC hilt
                if (
                        random.random() > 0.8 and
                        b.Material.registry[axe_builder["head"]["material"]].physics in ('metal', 'precious')
                ):
                    hm = axe_builder["head"]["material"]
                else:
                    hm = b.Material.pick(
                        ['bone', 'wood'],
                        roll_tier(tier),
                        filter_func
                    )
                return hm

            axe_builder["handle"] = {"material": new_handle_material()}

            main_equipment_dict = {"constructor": axe_builder, 'tier': tier}
            main_hand_weapon = eq.Axe(size, tier_target=tier, equipment_dict=main_equipment_dict)

        elif main_hand_choice == 'Sword':
            # Generate dict for eq.Sword
            sword_builder: dict = {"blade": {"material": orc_blade_material()}, 'hilt': {}}

            # Hilt material and colors would be filled in by the constructor, but we need to exclude elven.
            def new_hilt_material():
                if random.random() > 0.4:  # 40% of the time, pick same material for hilt
                    hm = b.Material.pick(
                        ['metal', 'bone', 'wood'],
                        tier,
                        filter_func
                    )
                else:
                    hm = sword_builder["blade"]["material"]
                return hm

            sword_builder["hilt"]["material"] = new_hilt_material()

            # Get not-so pretty looking eq.Sword parts:
            sword_builder["hilt"]["str"] = random.choice([
              "<–]",
              "⊂=(",
              "=={",
              "<=Σ",
              "<≡E",
              "⊂═╣"]
            )

            # LONG and scary eq.Swords
            def make_blade(blade_parts):
                return blade_parts[0] * 5 + blade_parts[1]

            sword_builder["blade"]["str"] = make_blade(
                random.choice([
                    ["=", ">"],
                    ["≡", "⊃"],
                    ["≡", ">"],
                    ["Ξ", "∃"]
                ])
            )

            # Generate colors -- unpainted, of course:
            sword_builder['blade']["color"] = sword_builder['blade'].get(
                "color", b.Material.registry[sword_builder['blade']["material"]].generate()
            )

            def new_hilt_color():
                # If parts share material, share color
                if sword_builder['blade']["material"] == sword_builder['hilt']["material"]:
                    return sword_builder['blade']["color"]

                # Generate usual material color
                return b.Material.registry[sword_builder['hilt']["material"]].generate()

            sword_builder['hilt']["color"] = sword_builder['hilt'].get(
                "color", new_hilt_color()
            )

            main_equipment_dict = {"constructor": sword_builder, "tier": tier}
            main_hand_weapon = eq.Sword(size, tier_target=tier, equipment_dict=main_equipment_dict)

            # 2% of the orcs hold eq.Sword wrong way for comedic value
            if random.random() < 0.02:
                main_hand_weapon.surface = pygame.transform.flip(main_hand_weapon.surface, True, False)

        else:
            # Generate dict for eq.Spear
            # Strings: Long, sturdy eq.Spears
            spear_builder: dict = {
                "head":
                    {
                        'material': b.Material.pick(
                            ['metal', 'bone', 'mineral'],
                            tier,
                            filter_func
                        ),
                        'str': random.choice([
                            "≡>",
                            "=>",
                            "═-",
                            "▭>"
                        ])
                    },
                "shaft":
                    {
                        'material': b.Material.pick(
                            ['wood'],
                            tier,
                            filter_func
                        ),
                        'str': random.choice([
                            "<===––––––––",
                            "––===–––––––",
                            "════════════",
                            "━━━━━━━━━━━━"
                        ])[:10]
                    }
            }

            # Unpainted:
            for part in spear_builder:
                spear_builder[part]['color'] = b.Material.registry[spear_builder[part]["material"]].generate()

            main_equipment_dict = {"constructor": spear_builder, "tier": tier}
            main_hand_weapon = eq.Spear(size, tier_target=tier, equipment_dict=main_equipment_dict)

        return main_hand_weapon

    @staticmethod
    def get_shield(tier, size=BASE_SIZE, team_color=None):
        shield_builder = {
            "frame": {
                "material": b.Material.pick(
                    ["wood", "metal", "bone"],
                    tier,
                    filter_func=lambda x: (
                        x.name not in b.Material.collections["elven"] and
                        x.name not in b.Material.collections["celestial"] and
                        x.weight >= 1
                    )
                )
            }
        }

        shield_builder["plate"] = {
            "material": b.Material.pick(
                ['metal', 'wood'],
                tier,
                lambda x: (
                        x.name not in b.Material.collections['plateless_bone'] and
                        x.name not in b.Material.collections['elven'] and
                        x.name not in b.Material.collections['celestial'] and
                        b.Material.registry[shield_builder["frame"]["material"]].weight >= x.weight >= 1
                )
            )
        }

        # If specified, paint plate team color; otherwise let .generate handle it
        if team_color and b.Material.registry[shield_builder['plate']['material']].physics in PAINTABLE:
            shield_builder['plate']['color'] = team_color
            shield_builder['plate']['tags'] = ['painted']

        off_equipment_dict = {"constructor": shield_builder, "tier": tier}
        return eq.Shield(size, tier_target=tier, equipment_dict=off_equipment_dict)


class Skeleton(Humanoid):
    has_blood = False
    skirmish_spawn_rate = 4
    class_name = 'Skeleton'
    difficulty = 2.5
    knockback_resistance = 0.3

    def __init__(self, position, tier, team_color=None):
        # Modify stats according to tier
        body_stats = character_stats["body"]["Skeleton"].copy()
        ai_stats = character_stats["soul"]["Skeleton"].copy()
        portraits = character_stats["mind"]["Skeleton"].copy()

        body_stats["health"] += 20 * (tier - 1)
        body_stats["max_speed"] += tier / 3
        ai_stats["skill"] += -0.5 + tier / 2

        super().__init__(
            position,
            **body_stats,
            **colors['enemy'],
            faces=portraits,
            name=f"Skeleton Lv.{tier:.0f}"
        )

        self.equip(self.get_main(tier), 'main_hand')

        # Shield in 85% cases
        if random.random() < 0.85:
            shield = self.get_shield(tier=tier, team_color=team_color)
            self.equip(shield, 'off_hand')

        # Add AI:
        self.ai = AI(self, **ai_stats)

    @staticmethod
    def get_main(tier, size=BASE_SIZE) -> eq.Wielded:
        classes = eq.Mace, eq.Sword, eq.Spear, eq.Axe
        weights = 50, 30, 15, 15
        cls = random.choices(classes, weights)[0]

        def filter_func(x):
            return (
                    x.name not in b.Material.collections["celestial"] and
                    x.name not in b.Material.collections["silver"]
            )

        if cls is eq.Mace:
            # Generate dict for Mace
            mace_builder = {"head": {"material": b.Material.pick(
                ["metal", "precious", "mineral"],
                roll_tier(tier),
                filter_func
            )}}

            # Handle material and colors would be filled in by the constructor, but we need to exclude silver.

            def new_handle_material():
                # 20% of the time, pick same metal for METALLIC hilt
                if (
                        random.random() > 0.8 and
                        b.Material.registry[mace_builder["head"]["material"]].physics in ('metal', 'precious')
                ):
                    hm = mace_builder["head"]["material"]
                else:
                    hm = b.Material.pick(
                        ['bone', 'wood'],
                        roll_tier(tier),
                        filter_func
                    )
                return hm

            mace_builder["handle"] = {"material": new_handle_material()}

            main_equipment_dict = {"constructor": mace_builder, 'tier': tier}

        elif cls is eq.Sword:
            # Generate dict for eq.Sword
            sword_builder: dict = {
                "blade":
                    {"material": b.Material.pick(
                        ["metal", "precious"],
                        roll_tier(tier),
                        filter_func
                    )},
                'hilt': {}
            }

            # Hilt material and colors would be filled in by the constructor, but we need to exclude elven.
            def new_hilt_material():
                if random.random() > 0.4:  # 40% of the time, pick same material for hilt
                    hm = b.Material.pick(
                        ['metal', 'bone', 'wood'],
                        tier,
                        filter_func
                    )
                else:
                    hm = sword_builder["blade"]["material"]
                return hm

            sword_builder["hilt"]["material"] = new_hilt_material()

            main_equipment_dict = {"constructor": sword_builder, "tier": tier}

        elif cls is eq.Spear:
            # Generate dict for eq.Spear
            spear_builder: dict = {
                "head":
                    {
                        'material': b.Material.pick(
                            ['metal', 'bone', 'mineral'],
                            tier,
                            filter_func
                        )
                    },
                "shaft":
                    {
                        'material': b.Material.pick(
                            ['wood'],
                            tier,
                            filter_func
                        )
                    }
            }

            # Unpainted:
            for part in spear_builder:
                spear_builder[part]['color'] = b.Material.registry[spear_builder[part]["material"]].generate()

            main_equipment_dict = {"constructor": spear_builder, 'tier': tier}

        else:
            # Generate dict for eq.Axe
            axe_builder = {
                "head": {
                    "material": b.Material.pick(
                        ["metal", "precious", "mineral"],
                        roll_tier(tier),
                        filter_func
                    ),
                    "str": [
                        "╭┫_┣╮",
                        "(●▲●)",
                        " ┣H┫ "
                    ],
                }}

            # Handle material and colors would be filled in by the constructor, but we need to exclude elven.

            def new_handle_material():
                # 20% of the time, pick same metal for METALLIC hilt
                if (
                        random.random() > 0.8 and
                        b.Material.registry[axe_builder["head"]["material"]].physics in ('metal', 'precious')
                ):
                    hm = axe_builder["head"]["material"]
                else:
                    hm = b.Material.pick(
                        ['bone', 'wood'],
                        roll_tier(tier),
                        filter_func
                    )
                return hm

            axe_builder["handle"] = {"material": new_handle_material()}

            main_equipment_dict = {"constructor": axe_builder, 'tier': tier}

        return cls(size, tier_target=tier, equipment_dict=main_equipment_dict)

    @staticmethod
    def get_shield(tier, size=BASE_SIZE, team_color=None) -> eq.Shield:
        team_color = team_color or colors["paint8"]["black"]

        def filter_func(x):
            return (
                    x.name not in b.Material.collections["celestial"] and
                    x.name not in b.Material.collections["silver"]
            )

        # Skeletons always paint shield no matter the material
        shield_builder = {
            "tier": tier,
            "constructor": {
                "plate": {
                    "tags": "painted",
                    "color": team_color,
                    "str": "A♣∀"
                },
                "frame": {}
            }
        }

        # Add materials by usual rules + filter func
        shield_builder["constructor"]["frame"]["material"] = b.Material.pick(
            ['metal', 'wood', 'bone'],
            roll_tier(tier),
            filter_func
        )

        # Some bone-physics material should be excluded, as plates are not formed from them:
        # Shield plate must not be heavier than frame:
        frame_material_weight = b.Material.registry[shield_builder["constructor"]["frame"]["material"]].weight

        shield_builder["constructor"]["plate"]["material"] = shield_builder["constructor"]["plate"].get(
            "material",
            b.Material.pick(
                ['metal', 'wood', 'leather', 'bone'],
                roll_tier(tier),
                lambda x:
                    x.weight <= frame_material_weight and
                    x.name not in b.Material.collections['plateless_bone'] and
                    filter_func(x)
            )
        )

        return eq.Shield(size, tier_target=tier, equipment_dict=shield_builder)


# Player character class
class Player(Humanoid):
    drops_shields = False
    hit_immunity = 1.2
    remains_persistence = 0.3
    knockback_resistance = 0.8

    def __init__(self, position, species='Human'):
        self.species = species
        player_body = character_stats["body"][self.species].copy()
        player_body["agility"] *= 2

        super(Player, self).__init__(
            position,
            **player_body,
            **colors["player"],
            faces=character_stats["mind"][self.species],
            name=string["protagonist_name"]
        )

        # Face right when starting:
        self.flip(new_collision=0)

        # Scene interaction:
        self.inventory = b.Inventory(self, INVENTORY_SPACE)
        self.seen_loot_drops = False
        self.sees_enemies = False

        # Bump sound limit:
        self.last_bump = 0

        # Add a secondary stamina bar to replace the usual when no stamina is consumed
        main_stamina_bar_parameters = list(get_key(self.bars["stamina"], b.Bar.instance_cache))
        new_parameters = list(main_stamina_bar_parameters)
        # Change color:
        new_parameters[2] = c(colors['sp_special'])
        self.sp_passive = b.Bar(*new_parameters)

        # Set by scene:
        self.combo_counter = None

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
                    artifacts[x]["class"] in {"Shield", "Swordbreaker", "Katar", "Knife"} and
                    artifacts[x]["tier"] == 0,
                    artifacts
                )
            )
            off_hand_pick = random.choice(off_hand_lst), 'off_hand'
        else:
            off_hand_pick = off_hand_pick, 'off_hand'

        for weapon in (main_hand_pick, off_hand_pick):
            weapon_gen = eq.Wielded.registry[artifacts[weapon[0]]["class"]]
            generated = weapon_gen(BASE_SIZE, equipment_dict=artifacts[weapon[0]], roll_stats=False)
            self.equip(generated, weapon[1])

    # Player SP is drawn differently if no weapon consumes stamina
    def _draw_bars(self):
        self.weapons_drain = any(
            weapon for weapon in self.weapon_slots
            if (
                    self.slots[weapon] and
                    self.slots[weapon].aim_drain_modifier != 0 and
                    self.slots[weapon].stamina_ignore_timer <= 0
            )
        )
        return super(Player, self)._draw_bars()

    def _fill_bar_dicts(self, bar: str, drawn_bars: dict, bar_rects: dict):
        if bar == 'stamina' and not self.weapons_drain:
            drawn_bars[bar], bar_rects[bar] = self.sp_passive.display(self.stamina)
        else:
            super(Player, self)._fill_bar_dicts(bar, drawn_bars, bar_rects)

    def save(self) -> str:
        # All Player objects are mostly identical, main difference is equipment and species
        equipment_classes = {
            slot: item.class_name
            for slot, item in self.slots.items()
            if item
        }

        equipment_stats = dict()

        for slot, item in self.slots.items():
            if item:
                item.reset(self, reposition=False)
                equipment_stats[slot] = item.drop_json()

        player_json = {
            'species': self.species,
            'seen_ld': self.seen_loot_drops,
            'classes': equipment_classes,
            'stats': equipment_stats
        }

        return json.dumps(player_json, sort_keys=False)

    @classmethod
    def load(cls, json_string: str, position=None):
        saved_state = json.loads(json_string)

        equipment_reg = eq.Wielded.registry.copy()
        equipment_reg.update(eq.Hat.registry)

        saved_classes = {
            slot: equipment_reg[tp_str]
            for slot, tp_str in
            saved_state['classes'].items()
        }

        player = cls(position, species=saved_state['species'])
        player.seen_loot_drops = saved_state['seen_ld']

        # Create and equip saved weapons:
        for slot, tp in saved_classes.items():
            item = tp(tier_target=1, size=player.size)
            item.from_json(saved_state['stats'][slot])
            player.equip(item, slot)

        return player


# Dummy creation
def make_dummy(cls, *args, hp=None, **kwargs):
    dummy = cls(*args, **kwargs)
    dummy.ai = DebugAI(dummy)
    dummy.knockback_resistance = 1
    dummy.weight = 1000
    if hp is not None:
        dummy.hp = dummy.max_hp = hp
    return dummy
