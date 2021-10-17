# todo:
#  Bar for Axe charge
#  Bar for shield equipping
#  Katar: offhand weapon that can't parry, but has non-interrupting bleeding stab attack with low sp cost
#  Katar has static damage
#  Holding activation prevents katar from retracting (in_use + continuous_input) and skewers enemy
# After tech demo
# todo:
#  shield can't spawn kickers too often
#  ?? Burning weapons
#  ?? Mace: activateable main hand weapon, copies falchion activation, increases collision damage to hit characters
#  ?? Knife: offhand weapon that deals crit damage to airborne, disabled or turned away characters
#  Add hats: armor, that passively changes stats of characters. Can be light, magic or heavy
#  activateable axes and maces
#  If mace is channeled, slowly spin up, ignoring limitations and aiming angle
#  Add projectiles,
#  activatable buckler: smaller, lighter shield with throw attack and lower stamina efficiency
#  axe can be channelled, to immobilize self and power up a boomerang throw
#  Add bows, crossbows: off-hand projectile weapons; replace main weapon when used:
#  -bow deals damage depending on drawn time
#  -crossbow can only deals max damage, but requires being fully loaded

from base_class import *
from particle import Kicker, MouseHint, Spark, DustCloud


# Define equipment classes:
class Nothing(Equipment):
    held_position = v()
    default_angle = 0
    hides_hand = False

    def __bool__(self):
        return False

    def __init__(self):
        super().__init__()
        self.last_angle = 0
        self.activation_offset = v()
        self.lock_timer = 0
        self.disabled = False
        self.dangerous = False

    def aim(self, hilt_placement, aiming_vector, character):
        self.last_angle = aiming_vector.as_polar()[1]

    def activate(self, character, continuous_input):
        # todo: punch! stuns and displaces enemy, minimal damage
        pass

    def lock(self, duration, angle=None, inertia=None):
        pass

    def reset(self, character):
        pass

    def description(self):
        return

    def limit_speed(self):
        return 1.0


class Hat(Equipment):
    prefer_slot = 'hat'


class Wielded(Equipment):
    registry = {}
    """Weapons, shields"""
    aim_drain_modifier = 1.0
    default_angle = 0
    max_tilt = None
    hitting_surface = "blade"
    return_time = 0.4
    prefer_slot = "main_hand"
    pushback = 1.0
    hides_hand = False
    held_position = v()
    can_parry = True

    def reset(self, character):
        self.last_angle = self.default_angle if character.facing_right else \
            math.copysign(180, self.default_angle)-self.default_angle

        self.angular_speed = 0
        self.in_use = False
        self.disabled = True  # Will be overriden frame after
        self.dangerous = False
        self.lock_timer = 0
        self.activation_offset = v()
        self.inertia_vector = v()
        self.tip_delta = v()

        # Calculate hitbox and position
        if character.position:
            self.hilt_v = (
                v(character.body_coordinates[self.prefer_slot]) +
                v(character.position) +
                v(self.held_position)
            )

            if self.length:
                self.tip_v = v()
                self.tip_v.from_polar((self.length, -self.last_angle))
                self.tip_v += self.hilt_v
        else:
            self.hilt_v = None
            self.tip_v = None

    def __init__(self, size, color=None, tier_target=None, equipment_dict=None):
        super().__init__(size, color=None, tier_target=None, equipment_dict=equipment_dict)
        self.hilt = None

        # Remember for generation scripts
        self.font_size = size

        # Depend on Material.registry and quality
        self.length = None
        self.weight = 0
        self.agility_modifier = None
        self.stamina_drain = None

        # Physical locations tethered to hilt start
        self.hilt_v = None
        self.tip_v = None
        self.tip_delta = v()

        # To remember last frame state for calculations
        self.angular_speed = 0
        self.last_angle = 0
        self.forced_angle = None

        # For movement and logic
        self.inertia_vector = v()
        self.activation_offset = v()
        self.lock_timer = 0
        self.disabled = False
        self.dangerous = False
        self.stamina_ignore_timer = 0

        # Fill attributes according to tier: called by subclasses
        self.damage_range = 0, 0
        self.color = color
        self.generate(size, tier_target)
        self.update_stats()
        # Randomize damage and other values
        if self.damage_range != (0, 0):
            self.damage_range = round(triangle_roll(self.damage_range[0], 0.07)), \
                                round(triangle_roll(self.damage_range[1], 0.07))
        if self.agility_modifier is not None:
            self.agility_modifier = triangle_roll(self.agility_modifier, 0.07)
        if self.stamina_drain is not None:
            self.stamina_drain = triangle_roll(self.stamina_drain, 0.07)
        self.loot_cards[None] = LootCard(self)

        # Attacks color may be updated by .generate
        self.color = color or self.color

        # Arrows to show activation direction:
        self.active_arrow = ascii_draw(size, "➤", self.color or colors["player"]["attacks_color"])

        # Moving weapons may create trails
        # Draw 0.2s worth of frames of weapon last position if it's fast enough to do damage
        self.trail_frames: list = [None] * int(FPS_TARGET * 0.03)
        self.frame_counter = 0  # only log every 3rd frame

        # Durability counter:
        self.durability = 100

    def show_stats(self, compare_to=None):
        """
        Returns list of dicts with stats; returns 1 if stat is better than comparable stat of another weapon, -1 if
        worse
        """
        if compare_to is not None:
            comparison_dict = compare_to.show_stats()
        else:
            comparison_dict = dict()

        stats_dict: dict = {
            "CLASS": {"text": self.builder["class"]},
            "TIER": {"text": self.tier, "value": self.tier},
            "DURABILTY": {"text": f"{self.durability}%", "value": self.durability}
        }
        if "TIER" in comparison_dict:
            stats_dict["TIER"]["evaluation"] = -1 * (comparison_dict["TIER"]["value"] - self.tier)

        if "DURABILTY" in comparison_dict:
            stats_dict["DURABILTY"]["evaluation"] = -1 * (comparison_dict["DURABILTY"]["value"] - self.durability)

        if self.damage_range != (0, 0):
            stats_dict["DAMAGE"] = {}

            if "DAMAGE" in comparison_dict:
                stats_dict["DAMAGE"]["evaluation"] = -1 * (comparison_dict["DAMAGE"]["average"] -
                                                           (self.damage_range[0]+self.damage_range[1])/2)
            stats_dict["DAMAGE"]["text"] = f'{self.damage_range[0]}-{self.damage_range[1]}'
            stats_dict["DAMAGE"]["average"] = (self.damage_range[0]+self.damage_range[1])/2

        if self.length:
            stats_dict["LENGTH"] = {
                "text": f'{self.length - self.length%5:.0f} cm',
                "value": (self.length - self.length % 5)
            }

            if "LENGTH" in comparison_dict:
                stats_dict["LENGTH"]["evaluation"] = (
                    (self.length - self.length % 5) - comparison_dict["LENGTH"]["value"]
                )

        stats_dict["SPEED"] = {"text": f'{self.agility_modifier * 100:.0f}', "value": self.agility_modifier}
        if "SPEED" in comparison_dict:
            stats_dict["SPEED"]["evaluation"] = -1 * (comparison_dict["SPEED"]["value"] - self.agility_modifier)

        if self.stamina_drain:
            stats_dict["DRAIN"] = {
                "text": f'{self.stamina_drain:.2f}',
                "value": self.stamina_drain
            }

            if "DRAIN" in comparison_dict:
                stats_dict["DRAIN"]["evaluation"] = comparison_dict["DRAIN"]["value"] - self.stamina_drain

        stats_dict["WEIGHT"] = {"text": f'{self.weight:.1f} kg'}

        return stats_dict

    def linear_tip_component(self):
        """Returns vector of linear speed of weapon tip caused from weapon rotation"""
        alpha = self.last_angle - 90
        x = self.angular_speed * self.length
        linear_v = v()
        linear_v.from_polar((x, alpha))
        return linear_v

    def aim(self, hilt_placement, aiming_vector, character):
        # Flip vectors and angles  if character is facing left:
        if not character.facing_right:
            if self.forced_angle is not None:
                if self.forced_angle > 0:
                    self.forced_angle = 180 - self.forced_angle
                else:
                    self.forced_angle = -180 - self.forced_angle
            aiming_vector.x *= -1
            if self.last_angle > 0:
                self.last_angle = 180 - self.last_angle
            else:
                self.last_angle = -180 - self.last_angle
            self.angular_speed *= -1

        # Tick down stamina ignore timer:
        if self.stamina_ignore_timer > 0:
            self.stamina_ignore_timer -= FPS_TICK

        # If weapon is locked, tick down timer and move by inertia offset(unless disabled) if needed:
        if self.lock_timer > 0:
            self.lock_timer -= FPS_TICK

            if self.inertia_vector != v() and not self.disabled:
                # Shields only move up to certain point:
                if isinstance(self, Shield) and self.held_counter >= self.equip_time:
                    pass
                else:
                    self.activation_offset += self.inertia_vector * FPS_TICK
                # Move hitbox (hilt and tip):
                self.hilt_v = hilt_placement.xy + self.activation_offset

            # Temporarily disable stamina drain once lock runs out:
            if self.lock_timer <= 0 and not isinstance(self, Shield):
                self.stamina_ignore_timer = 0.3

        # Otherwise, if offset remains, move weapon to place after lock is over:
        elif self.activation_offset != v() or (self.lock_timer >= 0 and self.disabled):

            # Test if activation offset and inertia vector are alligned; if yes, create a new vector to return in place:
            if (
                    self.inertia_vector == v() or
                    self.inertia_vector.x * self.activation_offset.x > 0 or
                    self.inertia_vector.y * self.activation_offset.y > 0
            ):
                # Return to place in weapon fixed time
                # Yes, I know it's squared
                new_vector = v(
                    -self.activation_offset.x * FPS_TICK / self.return_time,
                    -self.activation_offset.y * FPS_TICK / self.return_time
                )
                self.inertia_vector = new_vector

            if 4 * self.inertia_vector.length_squared() >= self.activation_offset.length_squared():
                self.inertia_vector = v()
                self.activation_offset = v()
            else:
                self.activation_offset += self.inertia_vector

            self.forced_angle = None
            self.disabled = False

        # Always make sure weapon is not locked anymore
        else:
            self.in_use = False
            self.forced_angle = None
            self.disabled = False

        # Unless weapon is locked, find targetting angle to determine acceleration:
        if self.forced_angle is not None:
            aiming_angle = self.forced_angle
        else:
            # First, calculate angle between current input points
            # If target is too close to weapon, ignore targeting
            if aiming_vector.length_squared() < BASE_SIZE ** 2:
                aiming_angle = self.last_angle
            else:
                aiming_angle = -aiming_vector.as_polar()[1]

            # If aiming angle is more than max tilt in same direction, set it to max angle
            if abs(aiming_angle) > self.max_tilt:
                aiming_angle = math.copysign(self.max_tilt, self.last_angle)

        # Find aiming direction:
        angle_delta = aiming_angle - self.last_angle

        # Determine speed change and modify angular_speed
        if angle_delta != 0:
            # Calculate acceleration modifier
            # Move faster when forced
            if self.forced_angle is not None:
                exhaust_mod = 2
            elif 0 < character.stamina <= 0.25 * character.max_stamina:
                exhaust_mod = ((character.stamina * 0.95 / character.max_stamina) + 0.05)
            else:
                exhaust_mod = 1

            max_speed = MAX_SPEED * exhaust_mod
            # Calculate acceleration
            acceleration = self.character_specific['acceleration'] * exhaust_mod
            acceleration = math.copysign(acceleration, angle_delta)

            # Calculate new speed
            new_speed = self.angular_speed + acceleration

            # If speed changes sign, anchor the rotation
            if new_speed * self.angular_speed < 0:
                speed_delta = 0
                self.angular_speed = 0
            # Limit max rotation speed:
            elif abs(new_speed) > MAX_SPEED:
                speed_delta = 0
                self.angular_speed = math.copysign(max_speed, new_speed)
            else:
                speed_delta = abs(self.angular_speed) - new_speed
                self.angular_speed = new_speed
        else:
            speed_delta = 0

        if self.angular_speed != 0:
            # Calculate resulting angle from previous position and current speed
            target_angle = self.last_angle + self.angular_speed
            if target_angle > 180:
                target_angle = target_angle - 360
            elif target_angle < -180:
                target_angle = target_angle + 360

            # If max_tilt is reached for equipment, hit limit and reset speed
            if self.max_tilt < abs(target_angle):
                self.last_angle = math.copysign(self.max_tilt, self.last_angle)
                self.angular_speed = 0
                speed_delta = 0
            # If aiming angle is between last and target angle, snap to it:
            elif min(self.last_angle, target_angle) - 2 < aiming_angle < max(self.last_angle, target_angle) + 2:
                self.last_angle = aiming_angle
                self.angular_speed = 0
                speed_delta = 0
            else:
                self.last_angle = target_angle

            # Normalize
            if self.last_angle > 180:
                self.last_angle = self.last_angle - 360
            if self.last_angle < -180:
                self.last_angle = self.last_angle + 360

        # If speed is changing, drain stamina; disabled or recently locked weapons don't drain stamina
        if speed_delta != 0 and not self.disabled and self.stamina_ignore_timer <= 0:
            character.stamina -= self.character_specific["stamina_drain"]
            # If stamina is empty, lock the weapon
            if character.stamina <= 0 < self.aim_drain_modifier:
                character.stamina = 0
                character.set_state('exhausted', 1)
                self.lock(duration=0.5, angle=self.last_angle)
                self.disabled = True

        # Flip vectors (back) if character is facing left:
        if not character.facing_right:
            if self.forced_angle is not None:
                if self.forced_angle > 0:
                    self.forced_angle = 180 - self.forced_angle
                else:
                    self.forced_angle = -180 - self.forced_angle
            if self.last_angle > 0:
                self.last_angle = 180 - self.last_angle
            else:
                self.last_angle = -180 - self.last_angle
            self.angular_speed *= -1

        self._calculate_hitbox(hilt_placement)

    def _calculate_hitbox(self, hilt_placement):
        # Calculate hitboxes
        # Move hilt and tip hitbox:
        self.hilt_v = hilt_placement.xy + self.activation_offset

        # Log location of the tip, if there is one
        if self.length:
            old_tip = self.tip_v
            self.tip_v = v()
            self.tip_v.from_polar((self.length, -self.last_angle))
            self.tip_v += self.hilt_v
            # Log tip movement vector for damage calculation:
            if old_tip is not None:
                self.tip_delta = self.tip_v - old_tip

        # Update self is dangerous
        self.dangerous = self.is_dangerous()

    def draw(self, character, _custom_surface=None):
        """Draw weapon at hilt position"""
        # Find original center of the image, as pygame will rotate the image around it
        center = self.surface.get_rect().center
        # Center is going to be rotated as vector around hilt as hilt_v
        center_vector = v(center) - v(self.hilt)
        center_vector.rotate_ip(-self.last_angle)
        # Now center is offset from fixed hilt
        if self.hilt_v is None:
            # Skip the frame
            return []
        center_vector += self.hilt_v

        # Prepare rectangle to be drawn at new center
        rotated_surface, rotated_rect = self._draw_raw(center_vector, _custom_surface or self.surface)

        if self.dangerous:
            rotated_surface = tint(rotated_surface, self.color or character.attacks_color)

            # Draw trails
            if self.frame_counter < 5:
                self.frame_counter += 1
            else:
                self.trail_frames.pop(0)
                trail = tint(rotated_surface, self.color or character.attacks_color)
                trail.set_alpha(127)
                self.trail_frames.append([trail, rotated_rect])
                self.frame_counter = 0
            return rotated_surface, rotated_rect, [trail for trail in self.trail_frames if
                                                   trail]  # append list of non-empty trails
        elif self.disabled:
            rotated_surface = tint(rotated_surface, c(colors["disabled_weapon"]))
            return rotated_surface, rotated_rect
        else:
            self.trail_frames: list = [None] * int(FPS_TARGET * 0.03 + 1)
            self.frame_counter = 0

        return rotated_surface, rotated_rect

    def _draw_raw(self, center_vector, custom_surface=None):
        rotated_surface = pygame.transform.rotate(custom_surface or self.surface, self.last_angle)
        rotated_rect = rotated_surface.get_rect(center=center_vector)
        return rotated_surface, rotated_rect

    def lock(self, duration, angle=None, inertia=None):
        """Force equipment to rotate and fix in a certain position for duration"""
        if angle is None:
            angle = self.last_angle

        # Remember for the future calculations
        self.lock_timer = duration
        self.forced_angle = angle

        # Don't change inertia unless specified:
        if inertia is not None:
            self.inertia_vector = inertia

    def hitbox(self):
        return self.hilt_v, self.tip_v

    def drop(self, character):
        """For animated scene.Remains, we require: surface, drawing rect, initial movement vector"""
        # No animation for non-existent characters
        if character.position is None:
            return

        # Set place if not set
        if self.hilt_v is None:
            self.reset(character)

        # Surface and Recxt are provided by .draw
        # Movement vector is character's speed with added random push between 60º and 120º
        speed = v()
        r_phi = character.max_speed, -random.randint(45, 135)
        speed.from_polar(r_phi)
        speed += 0.5 * self.tip_delta + 0.5 * character.speed

        self.disabled = False
        self.dangerous = False
        return *self.draw(character)[:2], speed

    def deal_damage(self, vector=v(), victim=None, attacker=None):
        return 0

    def parry(self, owner, opponent, other_weapon, calculated_impact=None):

        if owner.state not in DISABLED and owner.state not in BUSY:
            owner.set_state('active', 1)

        if not calculated_impact:
            # Calculate impact vector:
            own_component = self.tip_delta * self.weight
            enemy_component = other_weapon.tip_delta * other_weapon.weight
            collision_vector = enemy_component - own_component

            if not (
                    isinstance(other_weapon, Shield) or
                    (not self.dangerous and isinstance(other_weapon, Bladed) and other_weapon.spin_remaining > 0)
            ):
                other_weapon.parry(
                    owner=opponent,
                    opponent=owner,
                    other_weapon=self,
                    calculated_impact=-collision_vector
                )
        else:
            collision_vector = calculated_impact

        # Don't get parried if:
        #   -Enemy weapon was not dangerous,
        #   -Shields always parry back
        # Also, don't consume stamina
        if not (
                other_weapon.dangerous or
                abs(other_weapon.angular_speed) > SWING_THRESHOLD * 0.5 or
                isinstance(other_weapon, Shield)
        ):
            self.stamina_ignore_timer = 1
            return

        # Reset hand position:
        # if enemy_component == v():
        #     self.activation_offset = v()
        # else:
        #     self.activation_offset.scale_to_length(BASE_SIZE * 0.5)
        if other_weapon.tip_delta:
            self.activation_offset += other_weapon.tip_delta * other_weapon.weight / self.weight
        self.inertia_vector = v()

        # Separate impact force into 2 components:
        # 1. Parallel to weapon hitbox. Fully transformed into stamina damage and pushes character back
        # First, project collision on weapon hitbox:
        parallel_r = collision_vector.dot(self.tip_v - self.hilt_v) / self.length
        parallel_v = v()
        parallel_v.from_polar((parallel_r, self.last_angle))
        # 2. Perpendicular to weapon hitbox. Half is transformed into weapon rotation
        perpendicular_v = collision_vector - parallel_v

        # Process stamina damage, fully from parallel:
        stamina_damage = 0.01 * FPS_TARGET * abs(parallel_r)
        if self.stamina_ignore_timer > 0:
            stamina_damage *= 0.33

        owner.stamina -= stamina_damage
        owner.speed = v()

        if owner.stamina < 0:
            owner.stamina = 0
            owner.push(parallel_v / owner.weight, 0.5)

        # Kick away and disable self
        # I used to have crazy complicated logic here, but it's literally just cogwheel logic
        if other_weapon.angular_speed > 0:
            forced_angle_sign = 1
        else:
            forced_angle_sign = -1

        # Calculate forced angle depending on enemy weapon anglular speed and both weights
        angle_range = self.last_angle, forced_angle_sign * self.max_tilt
        speed_range = 0.5 * SWING_THRESHOLD, 1.6 * SWING_THRESHOLD
        if isinstance(other_weapon, Shield):
            enemy_actual_speed = -self.angular_speed
        else:
            # Modify it for weight difference and keep within range:
            enemy_actual_speed = abs(other_weapon.angular_speed) * other_weapon.weight / self.weight
            enemy_actual_speed = max(speed_range[0], enemy_actual_speed)
            enemy_actual_speed = min(speed_range[1], enemy_actual_speed)
            # todo: If above swing threshold, chance to disarm NPC

        # Forced angle is between min and max of angle range to the proportion of speed between min and max of speed:
        forced_angle = angle_range[0] + 0.91 * (angle_range[1] - angle_range[0]) * (
                enemy_actual_speed / SWING_THRESHOLD)

        # forced_angle = -math.copysign(85, self.last_angle)
        disable_time = perpendicular_v.length() / self.weight
        # Disable_time should be between 0.5s and 1.3s
        if disable_time > 1.3:
            disable_time = 1.3
        elif disable_time < 0.5:
            disable_time = 0.5

        # Half disable time for Players
        if owner.ai is None:
            disable_time *= 0.5

        self.disabled = True
        self.lock(disable_time, forced_angle)

    def portrait(self, rect: r, offset=BASE_SIZE*2, discolor=True):
        """
        Default display is to draw by placing hilt in OFFSET, OFFSET corner and pointing the tip in bottom right.
        Shield, Spear and Dagger may use different logic
        """
        surface = s(rect.size, pygame.SRCALPHA)

        # Find vertical scale to fill the rectangle:
        scale = (rect.width-2*offset)/self.surface.get_rect().height
        portrait = pygame.transform.rotozoom(self.surface, -40, scale)
        if discolor:
            if self.durability > 0:
                color = c(colors["inventory_text"])
            else:
                color = c(colors["inventory_broken"])

            portrait = tint(portrait, color)

        if isinstance(self, (Spear, Axe, Katar)):
            portrait = pygame.transform.flip(portrait, True, True)
        new_width = portrait.get_width()

        surface.blit(portrait, portrait.get_rect(left=max(0, (rect.width - new_width)//2), top=offset//4))

        return surface

    def reduce_damage(self, penalty):
        self.damage_range = int(self.damage_range[0] * (1-penalty)),  int(self.damage_range[1] * (1-penalty))

    def on_equip(self, character):
        # Reset:
        self.character_specific = dict()
        # Fill:
        self.character_specific["stamina_drain"] = self.stamina_drain * 250 * FPS_TICK * self.aim_drain_modifier
        self.character_specific["acceleration"] = character.agility * self.agility_modifier * FPS_TICK * 6.67


class Bladed(Wielded):
    """Maces, Axes, Swords"""

    def __init__(self, *args, **kwargs):
        super(Bladed, self).__init__(*args, **kwargs)
        self.spin_remaining = 0
        self.locked_from_activation = False  # Support for spin-granting activation

    def is_dangerous(self):
        if self.tip_v is None:
            return False
        parent = super(Bladed, self).is_dangerous()
        if parent:
            return True
        return not self.disabled and abs(self.angular_speed) >= SWING_THRESHOLD

    def deal_damage(self, vector=v(), victim=None, attacker=None):
        # Process limit cases:
        if abs(self.angular_speed) <= SWING_THRESHOLD or self.spin_remaining > 0:
            return self.damage_range[0]

        if abs(self.angular_speed) >= 1.6 * SWING_THRESHOLD:
            return self.damage_range[1]

        # Assume a cubic dependence instead of LERP becuase it has close to desired value spread
        # Calculate function constants:
        # Moved to on_equip

        # Finaly, calculate damage:
        damage = self.character_specific["coefficient"] * ((abs(self.angular_speed) -
                                                            self.character_specific["swing_mid_point"]) ** 3) + \
            self.character_specific["damage_mid_point"]

        # Calculation logic stays here in case I need to check myself:
        # equations: damage(swing_mid_point) = damage_mid_point
        # But they are effectively 0 on graph.
        # So: damage_x = coefficient * (swing_x - swing_mid_point) ^ 3 + damage_mid_point
        # how to find coefficient? take values at known point:
        # damage_max = coefficient * (swing_max - swing_mid_point) ^ 3 + damage_mid_point
        # damage_max = coefficient * (0.6 * SWING_THRESHOLD) ^ 3 + damage_mid_point
        # damage_max = 0.216 * coefficient * SWING_THRESHOLD ^ 3 + damage_mid_point
        # coefficient = (1/0.216))*(damage_max - damage_mid_point) * (SWING_THRESHOLD ** -3)

        return damage

    def _spin(self, speed, abs_angle):
        """Force self to spin with set speed for duration"""
        if speed == 0:
            print(f"Someone attempts to spin {self} with no spin")
            return

        self.angular_speed = speed
        self.spin_remaining = abs_angle
        self.stamina_ignore_timer = abs_angle / abs(self.angular_speed) * FPS_TICK

        # Reset position:
        self.lock_timer = 0
        self.activation_offset = v()

    def aim(self, hilt_placement, aiming_vector, character):

        if self.spin_remaining <= 0:
            super(Bladed, self).aim(hilt_placement, aiming_vector, character)
            return

        elif self.disabled:
            self.spin_remaining = 0
            super(Bladed, self).aim(hilt_placement, aiming_vector, character)
            return

        else:
            # Spin without any angle restrictions and stamina consumption
            self.stamina_ignore_timer -= FPS_TICK
            self.spin_remaining -= abs(self.angular_speed)
            self.last_angle += self.angular_speed

            # Normalize angle to pygame constraints (-180, 180):
            self.last_angle %= 360
            if -360 < self.last_angle < -180:
                self.last_angle += 360
            if 360 < self.last_angle < 180:
                self.last_angle -= 360

            character.set_state('active', 0.2)

            self._calculate_hitbox(hilt_placement)

            # Spawn particle along the hitbox (Approx. 14/s)
            if random.random() < FPS_TICK * 14:
                spark_position = random_point(*self.hitbox())
                spark_speed = random.triangular(0.2, 0.5) * self.tip_delta
                self.particles.append(
                    Spark(
                        spark_position,
                        spark_speed,
                        weapon=self,
                        attack_color=self.color,
                        lifetime=REMAINS_SCREENTIME*0.0625
                    )
                )

    def _calculate_hitbox(self, hilt_placement):
        super(Bladed, self)._calculate_hitbox(hilt_placement)
        # If spinning, reflect tip_delta to face outwards, to throw characters and weapons away from self:
        if self.spin_remaining > 0:
            fake_tip_delta = v()
            fake_tip_delta.from_polar((
                self.tip_delta.length(),
                -self.last_angle
            ))
            self.tip_delta = fake_tip_delta

    def reset(self, character):
        super(Bladed, self).reset(character)
        self.spin_remaining = 0

    def on_equip(self, character):
        super(Bladed, self).on_equip(character)
        self.character_specific["swing_mid_point"] = 1.3 * SWING_THRESHOLD
        self.character_specific["damage_mid_point"] = (self.damage_range[1] + self.damage_range[0]) / 2
        self.character_specific["coefficient"] = 9.2 * (self.damage_range[1] - self.damage_range[0]) * \
            (SWING_THRESHOLD ** -3)


class Pointed(Wielded):
    """Spears, Daggers, Swords"""
    stab_cost = 0.5
    stab_modifier = 1.0
    stab_dash_modifier = 1.0

    def __init__(self, *args, **kwargs):
        self.skewering_surface = None
        super(Pointed, self).__init__(*args, **kwargs)
        # Skewer execution:
        self.reduced_agility_modifier = self.agility_modifier
        self.saved_agility_modifier = self.agility_modifier
        self.kebab = None
        self.skewer_duration = self.max_skewer_duration = 0
        self.kebab_size = None

    def activate(self, character, continuous_input):
        """Drains stamina to dash in aimed direction, damaging enemies with weapon tip"""
        # Filter held mouse button and prevent actual multiple activation (input lag)
        if continuous_input or self.lock_timer > 0 or self.activation_offset != v():
            return

        # Need at least half max stamina
        if character.stamina <= self.character_specific["abs_stab_cost"]:
            character.set_state('exhausted', 1)
            return

        self._stab(character)

    def _stab(self, character, supplemental_v=None):
        if supplemental_v is None:
            supplemental_v = v()

        # Drain stamina. Drain more if character speed has opposite direction
        character.stamina *= self.stab_cost

        # Drain more unless we are a Short:
        if not isinstance(self, Short):
            cos = math.cos(math.radians(self.last_angle))
            sin = math.sin(math.radians(self.last_angle))
            if cos * character.speed.x < 0:
                character.stamina *= 0.5
            else:
                character.stamina *= 1 - 0.2 * abs(sin)

        # Make character dash:
        duration = 0.2
        dash_vector = v()
        dash_vector.from_polar((self.character_specific["abs_dash_speed"], -self.last_angle))
        character.speed += dash_vector

        # Lock all other currently equipped equipment, unless we are using SB/Katar or equipment is SB/Katar
        if not isinstance(self, (Swordbreaker, Katar)):
            for slot in character.weapon_slots:

                if self != character.slots[slot] and not isinstance(character.slots[slot], (Swordbreaker, Katar)):
                    weapon = character.slots[slot]
                    # Daggers and Swordbreakers are kept active
                    weapon.disabled = True
                    weapon.lock(angle=weapon.default_angle, duration=duration)

        # Determine activation_offset to move weapon forward (stab)
        self.inertia_vector = v()
        self.inertia_vector.from_polar((
            self.character_specific["stab_inertia_v"],
            -self.last_angle
        ))
        self.inertia_vector += supplemental_v

        # Dashing backwards is slower
        if (self.inertia_vector.x > 0) != character.facing_right:
            self.inertia_vector.x *= 0.25

        # Lock self
        self.in_use = True
        self.lock(angle=self.last_angle, duration=duration, inertia=self.inertia_vector)

        # Dash!
        if dash_vector != v():
            character.push(character.speed, duration, state="active")

    def is_dangerous(self):
        parent = super().is_dangerous()
        if parent:
            return True

        if self.tip_v is None:
            return False

        # Project weapon movement on weapon itself to determine "poking" component of weapon speed
        # To do this, divide dot product by length of the weapon "vector" (since it is known and constant)
        poke_strength = self.tip_delta.dot(self.tip_v - self.hilt_v) / self.length

        return poke_strength >= POKE_THRESHOLD and not self.disabled

    def deal_damage(self, vector=v(), victim=None, attacker=None):
        # If we stab a target that is skewered on another weapon, spawn "EXECUTION" kicker
        if victim and attacker:
            for weapon in attacker.weapon_slots:
                try:
                    if attacker.slots[weapon].kebab == victim:

                        execution_kicker = Kicker(
                            position=v(self.tip_v) + v(0, BASE_SIZE),
                            damage_value=0,
                            color=colors["crit_kicker"],
                            override_string='EXECUTION!',
                            oscillate=False
                        )
                        self.particles.append(execution_kicker)
                        return self.damage_range[1]

                except AttributeError:
                    continue

        hitting_v = self.tip_delta + vector

        # Project weapon hit on weapon itself to determine "poking" component of collision vector
        # To do this, divide dot product by length of the weapon "vector" (since it is known and constant)
        poke_strength = hitting_v.dot(self.tip_v - self.hilt_v) / self.length

        relative_poke = (poke_strength - POKE_THRESHOLD) / (2 * POKE_THRESHOLD)
        damage = round(lerp(self.damage_range, relative_poke))

        return damage

    def on_equip(self, character):
        super(Pointed, self).on_equip(character)
        self.character_specific["abs_stab_cost"] = character.max_stamina * self.stab_cost
        self.character_specific["abs_dash_speed"] = math.sqrt(self.agility_modifier) * BASE_SIZE * 15 * FPS_TICK * \
            self.stab_dash_modifier
        self.character_specific["stab_inertia_v"] = 6.25 * BASE_SIZE * character.agility * self.stab_modifier * \
            self.agility_modifier

    def _skewer(self, character, victim):
        self.kebab = victim
        self.skewer_duration = self.max_skewer_duration = victim.hit_immunity * 2
        self.kebab_size = victim.size

        # Temporarily modify agility modifier depending on target weight
        self.reduced_agility_modifier = min(
            self.agility_modifier*0.5,
            self.agility_modifier * character.size / self.kebab_size
        )
        self.saved_agility_modifier = self.agility_modifier

        self.kebab.anchor(self.skewer_duration, weapon=self)

        # Anchor self and increase stamina
        character.anchor(self.skewer_duration*0.5)
        self.stamina_ignore_timer = self.skewer_duration + 1

        # Add particle kicker:
        skewer_kicker = Kicker(
            position=v(self.tip_v)+v(0, BASE_SIZE),
            damage_value=0,
            color=colors["lightning"],
            override_string='SKEWER!' if random.random() < 0.95 else 'KEBAB!',
            oscillate=False
        )
        self.particles.append(skewer_kicker)

        # Add a Bar for character:
        character.bars[self.prefer_slot] = Bar(
            max_value=self.skewer_duration,
            fill_color=self.color or character.attacks_color,
            **character.weapon_bar_options
        )
        character.__dict__[self.prefer_slot] = self.skewer_duration

    def draw(self, character, _custom_surface=None):
        return super(Pointed, self).draw(
            character,
            _custom_surface=_custom_surface or (self.skewering_surface if self.kebab else self.surface)
        )


class Sword(Bladed, Pointed):
    aim_drain_modifier = 0.8
    default_angle = 30
    max_tilt = 120
    upside = ["Activate to dash and stab", "Powerful swing and stab attacks"]
    class_name = "Sword"

    def generate(self, size, tier=None):

        # Fill missing parts of self.builder on the go:
        self.builder["constructor"] = self.builder.get("constructor", {})
        self.builder["tier"] = self.builder.get("tier", tier)

        # Use this for calculations from now on
        tier = self.builder["tier"]

        self.builder["class"] = "Sword"

        def make_blade(blade_parts):
            bladelen = random.randint(3, 5)
            # 20% time, shortswords may get a pretty Swordbreaker blade instead
            # if bladelen == 3 and random.random() < 0.2:
            #    return random.choice(parts_dict['swordbreaker']['blades'])
            return blade_parts[0] * bladelen + blade_parts[1]

        # Create a blade:
        self.builder["constructor"]["blade"] = self.builder["constructor"].get("blade", {})
        self.builder["constructor"]["blade"]["str"] = self.builder["constructor"]["blade"].get(
            "str", make_blade(random.choice(parts_dict['sword']['blades']))
        )

        self.builder["constructor"]["blade"]["material"] = self.builder["constructor"]["blade"].get(
            "material", Material.pick(['metal'], roll_tier(tier))
        )

        # Create a hilt
        self.builder["constructor"]["hilt"] = self.builder["constructor"].get("hilt", {})
        self.builder["constructor"]["hilt"]["str"] = self.builder["constructor"]["hilt"].get(
            "str", random.choice(parts_dict['sword']['hilts'])
        )

        def new_hilt_material():
            if random.random() > 0.4:  # 40% of the time, pick same material for hilt
                hm = Material.pick(['metal', 'bone', 'precious', 'wood'], roll_tier(tier))
            else:
                hm = self.builder["constructor"]["blade"]["material"]
            return hm

        self.builder["constructor"]["hilt"]["material"] = self.builder["constructor"]["hilt"].get(
            "material", new_hilt_material()
        )

        # Generate colors:
        self.builder["constructor"]['blade']["color"] = self.builder["constructor"]['blade'].get(
            "color", Material.registry[self.builder["constructor"]['blade']["material"]].generate()
        )

        def new_hilt_color():
            if 'painted' in set(self.builder["constructor"]['hilt'].get("tags", [])):
                return paint()

            # If parts share material, share color
            if self.builder["constructor"]['blade']["material"] == self.builder["constructor"]['hilt']["material"]:
                return self.builder["constructor"]['blade']["color"]

            # 10%, paint the hilt
            if Material.registry[self.builder["constructor"]['hilt']["material"]].physics in PAINTABLE and \
                    random.random() > 0.9:
                self.builder["constructor"]['hilt']['tags'] = ['painted']
                return paint()

            # Generate usual material color
            return Material.registry[self.builder["constructor"]['hilt']["material"]].generate()

        self.builder["constructor"]['hilt']["color"] = self.builder["constructor"]['hilt'].get(
            "color", new_hilt_color()
        )

        # Now that builder is filled, create visuals:
        hilt_str = self.builder["constructor"]["hilt"]["str"]
        blade_str = self.builder["constructor"]["blade"]["str"]
        hilt_material = self.builder["constructor"]["hilt"]["color"]
        blade_material = self.builder["constructor"]["blade"]["color"]

        self.surface = ascii_draws(
            size,
            (
                (hilt_str, hilt_material),
                (blade_str, blade_material)
            )
        )

        # Hold between 1st and second hilt character -- offset exactly 1 character
        self.hilt = self.surface.get_width() / len(hilt_str + blade_str), self.surface.get_height() * 0.5

        # Sword tip coordinate relative to hilt -- offset 1.25 character_positions
        self.length = self.surface.get_width() - self.hilt[0] * 1.25

        self.color = Material.registry[self.builder["constructor"]["blade"]["material"]].attacks_color

    def update_stats(self: Wielded):
        hilt_material = Material.registry[self.builder["constructor"]["hilt"]["material"]]
        blade_material = Material.registry[self.builder["constructor"]["blade"]["material"]]
        blade_len = len(self.builder["constructor"]["blade"]["str"])

        # Generate stats according to Material.registry
        self.weight = 1 + hilt_material.weight + blade_len * (1 + blade_material.weight)
        self.tier = int((hilt_material.tier+blade_material.tier)*0.5)

        # reduced for blade weight, increased for hilt tier
        # SQRT to bring closer to 1.0
        self.agility_modifier = math.sqrt((10.0 + hilt_material.tier) / (blade_len * blade_material.weight)) * .7
        # Increased for sword total weight, reduced for blade tier and hilt weight (1.3-1.6)
        # SQRT to bring closer to 1.0
        self.stamina_drain = math.sqrt(0.3 * self.weight /
                                       ((2 + blade_material.tier) * math.sqrt(hilt_material.weight)))

        # Calculate damage range depending on weight, size and tier:
        min_damage = int((40 + self.weight) * 1.08 ** (self.tier - 1))
        max_damage = int(min_damage * math.sqrt(1 + blade_len / 5))
        self.damage_range = min_damage, max_damage
        self.redraw_loot()

    def deal_damage(self, vector=v(), victim=None, attacker=None):
        stab = Pointed.deal_damage(self, vector)
        swing = Bladed.deal_damage(self, vector)
        return max(stab, swing)


class Spear(Pointed):
    default_angle = 60
    max_tilt = 110
    aim_drain_modifier = 1.75
    stab_modifier = 0.75
    hitting_surface = 'shaft'
    upside = [
        "Activate to stab and skewer enemy",
        "Shake off skewered enemy to bleed it",
        "Hold activation to hold closer"
    ]
    downside = ["No swing attacks"]
    class_name = "Spear"
    stab_dash_modifier = 0

    _max_fallback = 1.0
    _fallback_distance = 0.4

    def __init__(self, *args, **kwargs):
        self.bleed = 0.0

        super(Spear, self).__init__(*args, **kwargs)

        # Held position is dynamic:
        self.absolute_demotion = 0
        self.held_position = v()
        self.active_this_frame = False
        self.held_back_duration = 0

    def generate(self, size, tier=None):

        # Fill missing parts of self.builder on the go:
        self.builder["constructor"] = self.builder.get("constructor", {})
        self.builder["tier"] = self.builder.get("tier", tier)
        self.builder["class"] = "Spear"

        # Use this for calculations from now on
        tier = self.builder["tier"]

        # Create shaft:
        self.builder["constructor"]["shaft"] = self.builder["constructor"].get("shaft", {})
        self.builder["constructor"]["shaft"]["str"] = self.builder["constructor"]["shaft"].get(
            "str", random.choice(parts_dict['spear']['shafts'])[:random.randint(8, 10) + 1]
        )
        self.builder["constructor"]["shaft"]["material"] = self.builder["constructor"]["shaft"].get(
            "material",
            Material.pick(['wood', 'reed'], roll_tier(tier))
        )

        # Create spear head:
        self.builder["constructor"]["head"] = self.builder["constructor"].get("head", {})
        self.builder["constructor"]["head"]["str"] = self.builder["constructor"]["head"].get(
            "str", random.choice(parts_dict['spear']['heads'])
        )
        self.builder["constructor"]["head"]["material"] = self.builder["constructor"]["head"].get(
            "material", Material.pick(['metal', 'bone', 'mineral'], roll_tier(tier))
        )

        # Generate colors:
        def new_color(part):
            return Material.registry[self.builder["constructor"][part]["material"]].generate()

        self.builder["constructor"]['shaft']["color"] = self.builder["constructor"]['shaft'].get(
            "color", new_color("shaft")
        )
        self.builder["constructor"]['head']["color"] = self.builder["constructor"]['head'].get(
            "color", new_color("head")
        )

        # Now that builder is filled, create visuals:
        shaft_str = self.builder["constructor"]["shaft"]["str"]
        tip_str = self.builder["constructor"]["head"]["str"]
        tip_sk = self.builder["constructor"]["head"]["str"][:-1] + ' '
        shaft_color = self.builder["constructor"]["shaft"]["color"]
        tip_color = self.builder["constructor"]["head"]["color"]

        spear_builder = (shaft_str, shaft_color), (tip_str, tip_color)
        self.surface = ascii_draws(size, spear_builder)

        spear_builder_sk = (shaft_str, shaft_color), (tip_sk, tip_color)
        self.skewering_surface = ascii_draws(size, spear_builder_sk)

        pole_length = len(shaft_str + tip_str)
        # Hold at 3rd pole character
        self.hilt = self.surface.get_width() * 3 / pole_length, self.surface.get_height() * 0.5

        # Spear tip coordinate relative to hilt -- offset 1.25 character_positions
        self.length = self.surface.get_width() * (1 - 3 / pole_length)

        self.color = self.color = Material.registry[self.builder["constructor"]["shaft"]["material"]].attacks_color or \
            Material.registry[self.builder["constructor"]["head"]["material"]].attacks_color

    def update_stats(self):
        shaft_material = Material.registry[self.builder["constructor"]["shaft"]["material"]]
        tip_material = Material.registry[self.builder["constructor"]["head"]["material"]]
        shaft_len = len(self.builder["constructor"]["shaft"]["str"])

        # Generating stats according to Material.registry
        self.weight = 5 + shaft_material.weight * 0.5 * shaft_len + tip_material.weight
        self.tier = int((shaft_material.tier + tip_material.tier) * 0.5)

        # reduced for total weight, increased for shaft tier
        self.agility_modifier = math.sqrt(1 + 0.1 * shaft_material.tier) * (10 / shaft_len)
        # Increased for spear total weight and length, reduced for shaft tier
        self.stamina_drain = self.weight * 0.05 * math.sqrt(1 + 0.1 * shaft_len) * 0.7 /\
            math.sqrt(1 + 0.1 * shaft_material.tier)

        # Calculate damage range depending on weight and tier; longer range reduces damage,
        # Max damage is further increased by weight:
        min_damage = int((60 + 0.5 * self.weight) * 1.08 ** (tip_material.tier - 1))
        max_damage = int(math.sqrt(self.weight / 9.5) * int(min_damage * 1.3 / math.sqrt(shaft_len / 11)))
        self.damage_range = min_damage, max_damage
        self.redraw_loot()

        # Heavy and long spear have higher bleed intensity:
        self.bleed = 0.15 * triangle_roll(self.weight/12 - 0.033*(10-shaft_len), 0.07)

    def deal_damage(self, vector=v(), victim=None, attacker=None):

        dealt_damage = super(Spear, self).deal_damage(v(), victim, attacker)
        # Only player characters can skewer:
        if attacker.ai is not None:
            return dealt_damage

        # Execute skewer if we are:
        #  1. Actively stabbing
        #  2. Running forward
        #  3. Not actually killing the target
        #  4. Not skewering someone already
        #  5. Target is not shielded
        if all([
            self.in_use,
            not self.kebab,
            0 < dealt_damage < victim.hp,
            not victim.shielded
        ]):
            self._skewer(attacker, victim)

        return dealt_damage

    def show_stats(self, compare_to=None):
        stats_dict: dict = super().show_stats(compare_to=compare_to)

        if compare_to is not None:
            comparison_dict = compare_to.show_stats()
        else:
            comparison_dict = dict()

        stats_dict["BLEED"] = {
            "value": self.bleed,
            "text": f'{100*self.bleed:.1f}%/s'
        }

        if "BLEED" in comparison_dict:
            stats_dict["BLEED"]["evaluation"] = self.bleed - comparison_dict["BLEED"]["value"]

        return stats_dict

    def aim(self, hilt_placement, aiming_vector, character):

        # Reset held counters
        if self.disabled:
            self.in_use = False
            self.held_position = v()
            self.held_back_duration = 0
            self.active_this_frame = 0

        elif self.held_position != v() and not self.active_this_frame and not self.disabled and not self.in_use:
            # Execute stab
            self.held_back_duration = 0
            self.absolute_demotion = 0

            # Transfer held_position to activation_offset (supplemental_v does this)
            # self.activation_offset += self.held_position
            self.held_position = v()
            self.in_use = False

            # Calculate supplement_v
            supplement_v = self.held_position * -0.2 * FPS_TICK
            self._stab(character, supplement_v)

        super(Spear, self).aim(hilt_placement, aiming_vector, character)
        self.active_this_frame = False

        # If character is skewered, tick down skewer timer
        if self.skewer_duration > 0:
            # Temproarily modify agility modifier:
            self.agility_modifier = lerp(
                (self.reduced_agility_modifier, self.saved_agility_modifier),
                1 - self.skewer_duration / self.max_skewer_duration
            )
            self.skewer_duration -= FPS_TICK

            # Slow down owner:
            self.speed_limit = 0.5

            # Affect owner's weapon bar value:
            character.__dict__[self.prefer_slot] = self.skewer_duration

            # If tip reached SWING_THRESHOLD3/4, detach target
            if abs(self.angular_speed) > SWING_THRESHOLD*0.75:
                # Unanchor and push in same direction
                self.kebab.anchor_timer = 0
                push_v = v(self.tip_delta)
                push_v.scale_to_length(character.max_speed*character.size/self.kebab_size)

                # Throw charcter and bleed it
                self.kebab.push(push_v, self.kebab.hit_immunity*2)
                self.kebab.bleed(self.bleed, self.kebab.hit_immunity*2)

                # Reset own skewer and restore stamina
                self.skewer_duration = 0
                character.stamina = character.max_stamina

                # Add particle kicker:
                skewer_kicker = Kicker(
                    position=v(self.tip_v),
                    damage_value=0,
                    color=colors["crit_kicker"],
                    override_string='BLEEDING!'
                )
                self.particles.append(skewer_kicker)

                # Pop own bar:
                character.bars.pop(self.prefer_slot, None)

        # Else: make sure nothing is attached
        else:
            self.agility_modifier = self.saved_agility_modifier
            self.kebab = None
            self.skewer_duration = 0
            self.kebab_size = None

            # Pop own bar:
            character.bars.pop(self.prefer_slot, None)

    def activate(self, character, continuous_input):

        # AI doesn't need this. Not even balance-wise, this branches off simple stab only for player convenience
        if character.ai:
            super(Spear, self).activate(character, continuous_input)
            return

        # Need at least half max stamina or already moving held_offset
        if self.held_position == v() and character.stamina <= character.max_stamina * self.stab_cost:
            character.set_state('exhausted', 1)
            return

        self._hold_back(character)

        # Actual stab will be exececuted by .aim on release

    def _hold_back(self, character):
        self.active_this_frame = True
        self.in_use = True

        if self.held_back_duration < self._max_fallback:
            self.held_back_duration += FPS_TICK
            self.absolute_demotion += self.character_specific["hb_decrement"]
            decrement_args = (
                self.absolute_demotion if character.facing_right else -self.absolute_demotion,
                self.last_angle if character.facing_right else -self.last_angle
            )
            self.held_position.from_polar(decrement_args)

    def reset(self, character):
        super(Spear, self).reset(character)

        # Held position is dynamic:
        self.absolute_demotion = 0
        self.held_position = v()
        self.active_this_frame = False
        self.held_back_duration = 0

        self.reduced_agility_modifier = self.agility_modifier
        self.saved_agility_modifier = self.agility_modifier
        self.kebab = None
        self.skewer_duration = self.max_skewer_duration = 0
        self.kebab_size = None

    def on_equip(self, character):
        super(Spear, self).on_equip(character)
        self.character_specific["hb_decrement"] = self._fallback_distance * self.length * FPS_TICK / self._max_fallback


class Short(Pointed):
    """Daggers, Swordbreakers"""
    default_angle = 30
    max_tilt = 150
    aim_drain_modifier = 0.5
    stab_modifier = 1.5

    def update_stats(self):
        hilt_material = Material.registry[self.builder["constructor"]["hilt"]["material"]]
        blade_material = Material.registry[self.builder["constructor"]["blade"]["material"]]

        # Generate stats according to Material.registry
        self.weight = 1 + hilt_material.weight + 2 * (1 + blade_material.weight)
        self.tier = int((hilt_material.tier + blade_material.tier) * 0.5)

        # reduced for blade weight, increased for hilt tier
        self.agility_modifier = math.sqrt((10.0 + hilt_material.tier) / (2 * (1 + blade_material.weight)) * 0.6)
        # Increased for dagger total weight, reduced for blade tier and hilt weight (1.3-1.6)
        # SQRT to bring closer to 1.0
        self.stamina_drain = math.sqrt(self.weight / ((2 + blade_material.tier) * math.sqrt(hilt_material.weight)))

        # Calculate damage range depending on weight and tier:
        min_damage = int((60 + 0.5 * self.weight) * 1.08 ** (self.tier - 1))
        max_damage = int(min_damage * 1.2)
        self.damage_range = min_damage, max_damage
        self.redraw_loot()


class Dagger(Short, Bladed):
    class_name = "Dagger"
    upside = [
        "Activate to dash and stab",
        "Activate after parrying to roll thorugh"
    ]
    downside = ["Minimal damage on swing attacks"]

    def generate(self, size, tier=None):
        # Fill missing parts of self.builder on the go:
        self.builder["constructor"] = self.builder.get("constructor", {})
        self.builder["tier"] = self.builder.get("tier", tier)

        # Use this for calculations from now on
        tier = self.builder["tier"]

        self.builder["class"] = "Dagger"

        # Create a blade:
        self.builder["constructor"]["blade"] = self.builder["constructor"].get("blade", {})
        self.builder["constructor"]["blade"]["str"] = self.builder["constructor"]["blade"].get(
            "str", random.choice(parts_dict['dagger']['blades'])

        )
        self.builder["constructor"]["blade"]["material"] = self.builder["constructor"]["blade"].get(
            "material", Material.pick(['metal', 'bone'], roll_tier(tier))
        )

        # Create a hilt
        self.builder["constructor"]["hilt"] = self.builder["constructor"].get("hilt", {})
        self.builder["constructor"]["hilt"]["str"] = self.builder["constructor"]["hilt"].get(
            "str", random.choice(parts_dict['dagger']['hilts'])
        )

        def new_hilt_material():
            if random.random() > 0.7:  # 30% of the time, pick same material for hilt
                hm = Material.pick(['metal', 'bone', 'precious'], roll_tier(tier))
            else:
                hm = self.builder["constructor"]["blade"]["material"]
            return hm

        self.builder["constructor"]["hilt"]["material"] = self.builder["constructor"]["hilt"].get(
            "material", new_hilt_material()
        )

        # Generate colors:
        # Blade is never painted
        self.builder["constructor"]['blade']["color"] = self.builder["constructor"]['blade'].get(
            "color", Material.registry[self.builder["constructor"]['blade']["material"]].generate()
        )

        def new_hilt_color():
            if 'painted' in set(self.builder["constructor"]['hilt'].get("tags", [])):
                return paint()

            # If parts share material, share color
            if self.builder["constructor"]['blade']["material"] == self.builder["constructor"]['hilt']["material"]:
                return self.builder["constructor"]['blade']["color"]

            # 10%, paint the hilt
            if Material.registry[self.builder["constructor"]['hilt']["material"]].physics in PAINTABLE and \
                    random.random() > 0.9:
                self.builder["constructor"]['hilt']['tags'] = ['painted']
                return paint()

            # Generate usual material color
            return Material.registry[self.builder["constructor"]['hilt']["material"]].generate()

        self.builder["constructor"]['hilt']["color"] = self.builder["constructor"]['hilt'].get(
            "color", new_hilt_color()
        )

        hilt_str = self.builder["constructor"]["hilt"]["str"]
        blade_str = self.builder["constructor"]["blade"]["str"]
        hilt_material = self.builder["constructor"]["hilt"]["color"]
        blade_material = self.builder["constructor"]["blade"]["color"]

        self.surface = ascii_draws(
            size,
            (
                (hilt_str, hilt_material),
                (blade_str, blade_material)
            )
        )

        # Hold between 1st and second hilt character -- offset exactly 1 character
        self.hilt = self.surface.get_width() / len(hilt_str + blade_str), self.surface.get_height() * 0.5

        # Dagger tip coordinate relative to hilt -- offset 1.25 character_positions
        self.length = self.surface.get_width() - self.hilt[0] * 1.25

        self.color = Material.registry[self.builder["constructor"]["blade"]["material"]].attacks_color

    def deal_damage(self, vector=v(), victim=None, attacker=None):
        # Determine if stabbibg or swinging damage is dealt; swinging is always min damage
        return Pointed.deal_damage(self, vector, victim, attacker)

    def __init__(self, *args, **kwargs):
        self.roll_window = 0
        self.time_from_parry = 0
        self.last_parry = None

        super(Dagger, self).__init__(*args, **kwargs)

    def update_stats(self):
        super(Dagger, self).update_stats()
        # Roll cooldown depends reduced by hilt tier and increased by blade material weight
        self.roll_window = math.sqrt(
            1.5 * Material.registry[self.builder["constructor"]["blade"]["material"]].weight /
            (1 + 0.1 * Material.registry[self.builder["constructor"]["hilt"]["material"]].tier)
        ) + 0.2
        self.redraw_loot()

    def parry(self, owner, opponent, other_weapon, calculated_impact=None):
        super(Dagger, self).parry(owner, opponent, other_weapon, calculated_impact)

        # Note last parry
        # Only swordbreakers can provide roll while in use
        if owner.ai is None and (isinstance(self, Swordbreaker) or not self.in_use):
            self.time_from_parry = 0
            self.last_parry = opponent

            # Spawn mouse-hint particle for player Daggers roll
            offset = v(-2 * BASE_SIZE, 0) if self.prefer_slot == 'main_hand' else v(2 * BASE_SIZE, 0)

            roll_particle = MouseHint(
                relative_position=offset,
                lifetime=self.roll_window,
                text="ROLL!",
                size=BASE_SIZE * 2 // 3,
                color=c(colors["indicator_good"]),
                monitor=self.has_roll
            )
            self.particles.append(roll_particle)

            # Add a Bar for character:
            owner.bars[self.prefer_slot] = Bar(
                max_value=self.roll_window,
                fill_color=self.color or owner.attacks_color,
                **owner.weapon_bar_options
            )
            owner.__dict__[self.prefer_slot] = self.roll_window

    def aim(self, hilt_placement, aiming_vector, character):
        Wielded.aim(self, hilt_placement, aiming_vector, character)

        if (
                self.last_parry is None or
                self.time_from_parry > self.roll_window or
                self.last_parry.hp < 0 or
                self.last_parry.position is None
        ):
            self.time_from_parry = 0
            self.last_parry = None
            character.bars.pop(self.prefer_slot, None)
        else:
            self.time_from_parry += FPS_TICK
            character.__dict__[self.prefer_slot] = self.time_from_parry

    def activate(self, character, continuous_input):
        # Roll through last parried enemy (only for players)
        if (
            self.last_parry and
            not continuous_input and
            character.roll_cooldown <= 0
        ):
            # Get target position for roll direction and range
            roll_v = 4*FPS_TICK*(v(self.last_parry.position) - v(character.position))
            character.roll(roll_v)

            # Reset
            self.time_from_parry = 0
            self.last_parry = None
            return

        super(Dagger, self).activate(character, continuous_input)

    def reset(self, character):
        super(Dagger, self).reset(character)
        self.time_from_parry = 0
        self.last_parry = None

    def has_roll(self):
        return self.last_parry is not None

    def show_stats(self, compare_to=None):
        stats_dict: dict = super().show_stats(compare_to=compare_to)

        if compare_to is not None:
            comparison_dict = compare_to.show_stats()
        else:
            comparison_dict = dict()

        stats_dict["ROLL WINDOW"] = {
            "value": self.roll_window,
            "text": f'{self.roll_window:.2f}'
        }

        if "ROLL WINDOW" in comparison_dict:
            stats_dict["ROLL WINDOW"]["evaluation"] = self.roll_window - comparison_dict["ROLL WINDOW"]["value"]

        return stats_dict

    def draw(self, character, **kwargs):
        drawn = super(Dagger, self).draw(character, **kwargs)

        if not drawn:
            return

        if self.last_parry:
            arrow_v = v(self.last_parry.position) - v(character.position)
            arrow_v.scale_to_length(character.hitbox[0].width)
            arrow_position = character.position + arrow_v

            arrow_surface = pygame.transform.rotate(self.active_arrow, self.last_angle)
            arrow_rect = arrow_surface.get_rect(center=arrow_position)

            try:
                if not drawn[2]:
                    drawn = drawn[0], drawn[1], [[arrow_surface, arrow_rect]]
                else:
                    drawn = drawn[0], drawn[1], drawn[2].append([arrow_surface, arrow_rect])
            except IndexError:
                drawn = drawn[0], drawn[1], [[arrow_surface, arrow_rect]]

        return drawn


class Axe(Bladed):
    class_name = "Axe"
    _handle_length = 3
    _max_spins = 3
    _prepare_angle = 110
    _slow_down = 2

    max_tilt = 130
    default_angle = 40
    hitting_surface = 'head'
    upside = [f'Hold activation to charge whirlwind attack (up to {_max_spins} spins)']
    downside = ['Only swing attacks']

    def __init__(self, size, *args, **kwargs):
        self.wing_tips = {
            'cw': [v(), v()],
            'ccw': [v(), v()]
        }
        self.wing_tips_v = [v(), v()]

        # Activation support
        self.charge_time = 0
        self.full_charge_time = 1
        self.spins_charged = 0
        self.active_this_frame = False
        self.active_character_speed = None
        self.slow_down_timer = 0
        self.last_spin_crits = False

        super(Axe, self).__init__(size * 2 // 3, *args, **kwargs)  # Axes need to use smaller font to fit in

    def on_equip(self, character):
        super(Axe, self).on_equip(character)
        self.character_specific["time_per_spin"] = self.full_charge_time / self._max_spins

    def activate(self, character, continuous_input):
        """Hold mouse button to charge whirlwind attack"""
        # 1. Weapon is not locked by anything else
        # 2. Input is continious
        # 3. At least half stamina before start
        if (
                (self.lock_timer > 0 and not self.locked_from_activation) or
                not continuous_input or
                self.charge_time == 0 and character.stamina < 0.5 * character.max_stamina
        ):
            return

        self.active_this_frame = True
        if self.spins_charged < self._max_spins:  # prevent not being enough for 3 spins
            character.stamina = max(0, character.stamina - self.character_specific["stamina_drain"])
            character.set_state('active', 0.2)
            self.charge_time += FPS_TICK
            if self.charge_time // self.character_specific["time_per_spin"] > self.spins_charged:
                self.spins_charged += 1
                # Spawn counting kicker:
                count_kicker = Kicker(
                    size=BASE_SIZE,
                    position=v(self.tip_v),
                    damage_value=0,
                    color=colors["lightning"],
                    override_string=f'{self.spins_charged:.0f}',
                    oscillate=False
                )
                self.particles.append(count_kicker)

                # Spawn sparks if max count is reached
                self.last_spin_crits = True
                if self.spins_charged == self._max_spins:
                    for _ in range(5):
                        spark_v = v()
                        spark_v.from_polar((1.5 * SWING_THRESHOLD, random.uniform(-180, 180)))
                        spark = Spark(
                            position=v(self.tip_v),
                            weapon=None,
                            vector=spark_v,
                            attack_color=colors["lightning"],
                            lifetime=REMAINS_SCREENTIME * 0.0625
                        )
                        self.particles.append(spark)
        else:
            self.prevent_regen = True

        # Prevent use while charging:
        self.disabled = True
        self.lock(
            duration=FPS_TICK,
            angle=self._prepare_angle if character.facing_right else 180-self._prepare_angle,
            inertia=None,
            locked_from_activation=True
        )

        # Spin will be executed on release by .aim

    def hitbox(self):
        return self.wing_tips_v
    
    def _calculate_hitbox(self, hilt_placement):
        super(Axe, self)._calculate_hitbox(hilt_placement)
        new_hitbox = []
        direction = 'cw' if self.angular_speed < 0 else 'ccw'
        for wing_tip in self.wing_tips[direction]:
            # Rotate tip vector by last angle
            new_vector = v(wing_tip)
            new_vector.rotate_ip(-self.last_angle)
            new_vector += v(self.hilt_v)
            new_hitbox.append(new_vector)

        self.wing_tips_v = new_hitbox

    def generate(self, size, tier=None):

        # Fill missing parts of self.builder on the go:
        self.builder["constructor"] = self.builder.get("constructor", {})
        self.builder["tier"] = self.builder.get("tier", tier)

        # Use this for calculations from now on
        tier = self.builder["tier"]

        self.builder["class"] = "Axe"

        # Create axe head:
        self.builder["constructor"]["head"] = self.builder["constructor"].get("head", {})
        self.builder["constructor"]["head"]["str"] = self.builder["constructor"]["head"].get(
            "str", random.choice(parts_dict['axe']['heads'])
        )

        self.builder["constructor"]["head"]["material"] = self.builder["constructor"]["head"].get(
            "material", Material.pick(['precious', 'metal', 'mineral'], roll_tier(tier))
        )

        # Create a handle:
        self.builder["constructor"]["handle"] = self.builder["constructor"].get("handle", {})
        self.builder["constructor"]["handle"]["str"] = self.builder["constructor"]["handle"].get(
            "str", random.choice(parts_dict['axe']['handles'])
        )

        def new_handle_material():
            # 20% of the time, pick same metal for METALLIC hilt
            if (
                    random.random() > 0.8 and
                    Material.registry[self.builder["constructor"]["head"]["material"]].physics in ('metal', 'precious')
            ):
                hm = self.builder["constructor"]["head"]["material"]
            else:
                hm = Material.pick(['bone', 'wood'], roll_tier(tier))
            return hm

        self.builder["constructor"]["handle"]["material"] = self.builder["constructor"]["handle"].get(
            "material", new_handle_material()
        )

        # Generate colors:
        self.builder["constructor"]['head']["color"] = self.builder["constructor"]['head'].get(
            "color", Material.registry[self.builder["constructor"]['head']["material"]].generate()
        )

        # If axe is full-metal, use head color for handle
        def new_handle_color():
            if self.builder["constructor"]['head']['material'] == self.builder["constructor"]['handle']['material']:
                return self.builder["constructor"]['head']["color"]
            # Else, generate new
            return Material.registry[self.builder["constructor"]['handle']["material"]].generate()

        self.builder["constructor"]['handle']["color"] = self.builder["constructor"]['handle'].get(
            "color", new_handle_color()
        )

        # Now that builder is filled, create surface:
        handle_str = self._handle_length * ['  ' + self.builder["constructor"]["handle"]["str"] + '  ']
        head_str = self.builder["constructor"]["head"]["str"]
        handle_color = self.builder["constructor"]["handle"]["color"]
        head_color = self.builder["constructor"]["head"]["color"]

        self.surface = ascii_draw_rows(
            size, [[row, head_color] for row in head_str] + [[row, handle_color] for row in handle_str]
        )
        self.surface = pygame.transform.rotate(self.surface, -90)

        # Hold in the middle of handle
        relative_x = len(handle_str)*0.5 / len(head_str + handle_str)
        self.hilt = self.surface.get_width() * relative_x, self.surface.get_height() * 0.5

        # Sword tip coordinate relative to hilt -- offset 1.25 character_positions
        self.length = self.surface.get_width() - self.hilt[0]

        self.color = Material.registry[self.builder["constructor"]["head"]["material"]].attacks_color

        # Axe special: find locations of head corner vectors relative to the hilt
        blade_start = len(handle_str) / (len(head_str) + len(handle_str))
        self.wing_tips = {
            'cw': [
                v(self.surface.get_width()*blade_start, self.surface.get_height()) - v(self.hilt),
                v(self.surface.get_rect().bottomright) - v(self.hilt)
            ],
            'ccw': [
                v(self.surface.get_width()*blade_start, 0) - v(self.hilt),
                v(self.surface.get_rect().topright) - v(self.hilt)
            ]
        }

    def update_stats(self):
        handle_material = Material.registry[self.builder["constructor"]["handle"]["material"]]
        head_material = Material.registry[self.builder["constructor"]["head"]["material"]]

        # Generate stats according to Material.registry
        self.weight = 1.5 * handle_material.weight + 3 + 3 * head_material.weight
        self.tier = int((handle_material.tier + head_material.tier) * 0.5)

        # reduced for head weight, increased for handle tier
        # SQRT to bring closer to 1.0
        self.agility_modifier = math.sqrt((8.0 + handle_material.tier) / (3 * head_material.weight)) * .65
        # Increased for axe total weight, reduced for head tier (1.3-1.6)
        # SQRT to bring closer to 1.0
        self.stamina_drain = math.sqrt(0.3 * self.weight / (2 + head_material.tier))

        # Calculate damage range depending on weight, size and tier:
        # High tier axes scale better, weight is very important
        min_damage = int((450 + self.weight ** 2) / 7 * 1.08 ** (self.tier - 1))
        max_damage = int(min_damage * math.sqrt(2 + 0.1 * self.tier))
        self.damage_range = min_damage, max_damage

        # Charge time depends on total weight and tier
        weight_percentile = (self.weight - 6) / 2.5
        self.full_charge_time = triangle_roll(lerp((2, 3), weight_percentile) - 0.1*self.tier, 0.07)

        self.redraw_loot()

    def lock(self, duration, angle=None, inertia=None, locked_from_activation=False):
        self.locked_from_activation = locked_from_activation
        super(Axe, self).lock(duration, angle, inertia)

    def reset(self, character):
        super(Axe, self).reset(character)
        # Activation support
        self.charge_time = 0
        self.spins_charged = 0
        self.active_this_frame = False
        self.locked_from_activation = False
        self.active_character_speed = None
        self.last_spin_crits = False

    def aim(self, hilt_placement, aiming_vector, character):
        # Process spin activation:
        if not self.active_this_frame:
            self.prevent_regen = False
            if self.spins_charged > 0 and character.state not in DISABLED:
                self.disabled = False
                speed = -3*SWING_THRESHOLD if character.facing_right else 3*SWING_THRESHOLD
                self._spin(speed=speed, abs_angle=self.spins_charged*360)
                # Prevent character speed from changing:
                self.active_character_speed = 2*v(character.speed)
                self.speed_limit = 2
            elif self.spin_remaining <= 0:
                self.active_character_speed = None

            self.charge_time = 0
            self.spins_charged = 0
            self.active_this_frame = False
            self.locked_from_activation = False

        self.active_this_frame = False

        if self.spin_remaining > 0:
            character.speed = v(self.active_character_speed or character.speed)
        elif self.charge_time <= 0:
            self.prevent_regen = False

        current_spin = self.spin_remaining

        super(Axe, self).aim(hilt_placement, aiming_vector, character)

        # Once spin is over, apply fading slow
        if current_spin > 0 and self.spin_remaining <= 0:
            self.last_spin_crits = False
            character.set_state('exhausted', 1)
            self.slow_down_timer = self._slow_down
            self.disabled = True
            self.lock(
                self.slow_down_timer / 2,
                -self._prepare_angle if character.facing_right else -180 + self._prepare_angle
            )

        if self.slow_down_timer > 0:
            self.speed_limit = 1 - self.slow_down_timer / self._slow_down
            self.slow_down_timer -= FPS_TICK

    def show_stats(self, compare_to=None):
        stats_dict: dict = super().show_stats(compare_to=compare_to)

        if compare_to is not None:
            comparison_dict = compare_to.show_stats()
        else:
            comparison_dict = dict()

        stats_dict["FULL CHARGE"] = {
            "value": self.full_charge_time,
            "text": f'{self.full_charge_time:.1f}'
        }

        if "FULL CHARGE" in comparison_dict:
            stats_dict["FULL CHARGE"]["evaluation"] = comparison_dict["FULL CHARGE"]["value"] - self.full_charge_time

        return stats_dict
    
    def parry(self, owner, opponent, other_weapon, calculated_impact=None):
        beyblade_bump = False

        # Don't take pushback from shields while whirlwinding:
        if self.spin_remaining > 0 and isinstance(other_weapon, Shield):
            return

        # Ignore non-dangerous weapons while whirlwinding:
        elif self.spin_remaining > 0 and not other_weapon.dangerous:
            return

        # If we DO get parried while whirlwinding, push owner back
        elif self.spin_remaining > 0:
            # Activation support
            self.charge_time = 0
            self.spins_charged = 0
            self.active_this_frame = False
            self.locked_from_activation = False
            self.last_spin_crits = False

            beyblade_bump = True

        super(Axe, self).parry(owner, opponent, other_weapon, calculated_impact)

        # Kick owner back
        if beyblade_bump:
            owner.speed = v()
            pushback_v = v(-2 * POKE_THRESHOLD if owner.facing_right else 2 * POKE_THRESHOLD, -2 * POKE_THRESHOLD)
            owner.push(pushback_v, 1.2, affect_player=True)

    def deal_damage(self, vector=v(), victim=None, attacker=None):
        if 0 < self.spin_remaining < 360 and self.last_spin_crits:
            return self.damage_range[1]

        return super(Axe, self).deal_damage(vector, victim, attacker)


class Mace(Bladed):
    # class_name = 'Mace'
    hitting_surface = "head"
    max_tilt = 180
    pushback = 2.5
    action_string = "Hold action button to spin weapon up"
    """Heavy weapon with relatively low damage and disabling attack displacement"""


class Falchion(Sword):
    class_name = 'Falchion'
    aim_drain_modifier = 0.75
    default_angle = 30
    max_tilt = 150
    upside = ["Activate to roll in aiming direction"]
    downside = ["Minimal damage on stab attacks"]

    def __init__(self, *args, **kwargs):
        # To be set by update_stats
        self.roll_cooldown = 0
        super(Falchion, self).__init__(*args, **kwargs)
        self.roll_cooldown = triangle_roll(self.roll_cooldown, 0.07)

    def generate(self, size, tier=None):

        # Fill missing parts of self.builder on the go:
        self.builder["constructor"] = self.builder.get("constructor", {})
        self.builder["tier"] = self.builder.get("tier", tier)

        # Use this for calculations from now on
        tier = self.builder["tier"]

        self.builder["class"] = self.class_name

        # Create a blade:
        self.builder["constructor"]["blade"] = self.builder["constructor"].get("blade", {})
        self.builder["constructor"]["blade"]["str"] = self.builder["constructor"]["blade"].get(
            "str", random.choice(parts_dict['falchion']['blades'])
        )

        self.builder["constructor"]["blade"]["material"] = self.builder["constructor"]["blade"].get(
            "material", Material.pick(['metal'], roll_tier(tier))
        )

        # Create a hilt
        self.builder["constructor"]["hilt"] = self.builder["constructor"].get("hilt", {})
        self.builder["constructor"]["hilt"]["str"] = self.builder["constructor"]["hilt"].get(
            "str", random.choice(parts_dict['dagger']['hilts'])
        )

        def new_hilt_material():
            if random.random() > 0.6:  # 40% of the time, pick same material for hilt
                hm = Material.pick(['metal', 'bone', 'precious', 'wood'], roll_tier(tier))
            else:
                hm = self.builder["constructor"]["blade"]["material"]
            return hm

        self.builder["constructor"]["hilt"]["material"] = self.builder["constructor"]["hilt"].get(
            "material", new_hilt_material()
        )

        # Generate colors:
        self.builder["constructor"]['blade']["color"] = self.builder["constructor"]['blade'].get(
            "color", Material.registry[self.builder["constructor"]['blade']["material"]].generate()
        )

        def new_hilt_color():
            if 'painted' in set(self.builder["constructor"]['hilt'].get("tags", [])):
                return paint()

            # If parts share material, share color
            if self.builder["constructor"]['blade']["material"] == self.builder["constructor"]['hilt']["material"]:
                return self.builder["constructor"]['blade']["color"]

            # 10%, paint the hilt
            if Material.registry[self.builder["constructor"]['hilt']["material"]].physics in PAINTABLE and \
                    random.random() > 0.9:
                self.builder["constructor"]['hilt']['tags'] = ['painted']
                return paint()

            # Generate usual material color
            return Material.registry[self.builder["constructor"]['hilt']["material"]].generate()

        self.builder["constructor"]['hilt']["color"] = self.builder["constructor"]['hilt'].get(
            "color", new_hilt_color()
        )

        # Now that builder is filled, create visuals:
        hilt_str = self.builder["constructor"]["hilt"]["str"]
        blade_str = self.builder["constructor"]["blade"]["str"]
        hilt_material = self.builder["constructor"]["hilt"]["color"]
        blade_material = self.builder["constructor"]["blade"]["color"]

        self.surface = ascii_draws(
            size,
            (
                (hilt_str, hilt_material),
                (blade_str, blade_material)
            )
        )

        # Hold between 1st and second hilt character -- offset exactly 1 character
        self.hilt = self.surface.get_width() / len(hilt_str + blade_str), self.surface.get_height() * 0.5

        # Falchion tip coordinate relative to hilt -- offset 1.25 character_positions
        self.length = self.surface.get_width() - self.hilt[0] * 1.25

        self.color = Material.registry[self.builder["constructor"]["blade"]["material"]].attacks_color

    def update_stats(self):
        # Steal from swords, than increase damage range by 15%
        super().update_stats()
        # Increase damage
        self.damage_range = int(self.damage_range[0] * 0.85), int(self.damage_range[1] * 1.15)
        # Roll cooldown depends reduced by hilt tier and increased by blade material weight
        self.roll_cooldown = math.sqrt(
            1.5 * Material.registry[self.builder["constructor"]["blade"]["material"]].weight /
            (1 + 0.1 * Material.registry[self.builder["constructor"]["hilt"]["material"]].tier)
        ) + 0.2

    def deal_damage(self, vector=v(), victim=None, attacker=None):
        # Stab component is always min damage
        return Bladed.deal_damage(self, vector)

    def activate(self, character, continuous_input, point=None):
        if continuous_input or character.roll_cooldown > 0:
            return

        if point is None:
            point = v(pygame.mouse.get_pos())

        # Get mouse target for roll direction and range
        roll_v = point - v(character.position)

        # Modify/limit roll length (^2 is faster)
        if roll_v.length_squared() > (self.character_specific["roll_treshold"] * FPS_TARGET) ** 2:
            roll_v.scale_to_length(2 * self.character_specific["roll_treshold"])
        else:
            roll_v *= FPS_TICK * 2
        character.roll(roll_v, roll_cooldown=self.roll_cooldown)

    def show_stats(self, compare_to=None):
        stats_dict: dict = super().show_stats(compare_to=compare_to)

        if compare_to is not None:
            comparison_dict = compare_to.show_stats()
        else:
            comparison_dict = dict()

        stats_dict["ROLL DELAY"] = {
            "value": self.roll_cooldown,
            "text": f'{self.roll_cooldown:.2f}'
        }

        if "ROLL DELAY" in comparison_dict:
            stats_dict["ROLL DELAY"]["evaluation"] = comparison_dict["ROLL DELAY"]["value"] - self.roll_cooldown

        return stats_dict

    def calculate_roll(self, character):
        return

    def on_equip(self, character):
        super(Falchion, self).on_equip(character)
        self.character_specific["roll_treshold"] = character.max_speed * self.agility_modifier * character.size / \
            BASE_SIZE


class OffHand(Wielded):
    aim_drain_modifier = 0.0
    prefer_slot = "off_hand"


class Shield(OffHand):
    class_name = "Shield"
    hitting_surface = "plate"
    default_angle = -20
    max_tilt = 45
    return_time = 0.4
    hides_hand = True
    action_string = "Hold action button to block enemy attacks; Activate while running for shield bash"
    upside = ["Hold action button to block", "Activate while running to bash"]
    downside = ["Low damage", "Can't block from behind"]

    _rehit_immune = 0.4
    _grace_period = 0.3

    def parry(self, owner, opponent, other_weapon, calculated_impact=None):
        """Shields should use block instead"""
        pass

    def __init__(self, size, *args, **kwargs):
        self.held_counter = 0
        self.active_this_frame = False
        self.active_last_frame = False
        self.equip_time = 1  # updated by .generate
        super().__init__(size, *args, **kwargs)
        # Make sure damage is constant
        self.damage_range = self.damage_range[0], self.damage_range[0]
        self.redraw_loot()
        self.internal_immunity = 0
        self.reactivation_timer = 0

    def generate(self, size, tier=None):

        # Fill missing parts of self.builder on the go:
        self.builder["constructor"] = self.builder.get("constructor", {})
        self.builder["tier"] = self.builder.get("tier", tier)

        # Use this for calculations from now on
        tier = self.builder["tier"]

        self.builder["class"] = "Shield"

        # Create frames
        self.builder["constructor"]["frame"] = self.builder["constructor"].get("frame", {})
        self.builder["constructor"]["frame"]["str"] = self.builder["constructor"]["frame"].get(
            "str", random.choice(parts_dict['shield']['frames'])
        )
        self.builder["constructor"]["frame"]["material"] = self.builder["constructor"]["frame"].get(
            "material", Material.pick(['metal', 'reed', 'wood', 'bone'], roll_tier(tier))
        )

        # Create plate
        self.builder["constructor"]["plate"] = self.builder["constructor"].get("plate", {})
        self.builder["constructor"]["plate"]["str"] = self.builder["constructor"]["plate"].get(
            "str", random.choice(parts_dict['shield']['plates'])
        )
        # Some bone-physics material should be excluded, as plates are not formed from them:
        # Shield plate must not be heavier than frame:
        frame_material_weight = Material.registry[self.builder["constructor"]["frame"]["material"]].weight

        self.builder["constructor"]["plate"]["material"] = self.builder["constructor"]["plate"].get(
            "material",
            Material.pick(
                ['metal', 'wood', 'leather', 'bone'],
                roll_tier(tier),
                lambda x: x.weight <= frame_material_weight and x.name not in Material.collections['plateless_bone']
            )
        )

        # Frame is never painted:
        self.builder["constructor"]["frame"]["color"] = self.builder["constructor"]["frame"].get(
            "color", Material.registry[self.builder["constructor"]["frame"]["material"]].generate()
        )

        # Paint plate if possible:
        def new_plate_color():
            if 'painted' in set(self.builder["constructor"]['plate'].get("tags", {})):
                return paint()

            # 40%, paint the plate
            if Material.registry[self.builder["constructor"]['plate']["material"]].physics in PAINTABLE and \
                    random.random() > 0.6:
                self.builder["constructor"]['plate']['tags'] = ['painted']
                return paint()

            # Generate usual material color
            return Material.registry[self.builder["constructor"]['plate']["material"]].generate()

        self.builder["constructor"]['plate']["color"] = self.builder["constructor"]['plate'].get(
            "color", new_plate_color()
        )

        # Now that builder is filled, create visuals:
        left_str, right_str = self.builder["constructor"]["frame"]["str"]
        edge_color = self.builder["constructor"]["frame"]["color"]
        plate_str = self.builder["constructor"]["plate"]["str"]
        plate_color = self.builder["constructor"]["plate"]["color"]

        shield_builder = (left_str, edge_color), (plate_str, plate_color), (right_str, edge_color)

        self.surface = ascii_draws(size, shield_builder)

        self.hilt = self.surface.get_rect().center

        self.color = Material.registry[self.builder["constructor"]["plate"]["material"]].attacks_color or \
            Material.registry[self.builder["constructor"]["frame"]["material"]].attacks_color

    def update_stats(self):
        plate_material = Material.registry[self.builder["constructor"]["plate"]["material"]]
        frame_material = Material.registry[self.builder["constructor"]["frame"]["material"]]

        self.weight = 3 + plate_material.weight * 3 + frame_material.weight * 1.0
        self.tier = int((plate_material.tier + frame_material.tier)/2)

        # Determines dash distance, depends on frame tier:
        self.agility_modifier = 0.2 + 0.2 * frame_material.tier
        # Determines how much damage is converted into stamina loss; reduced by weight and plate tier
        self.stamina_drain = 1 + ((1 - 0.1 * self.weight) / math.sqrt(1 + 0.1 * plate_material.tier))
        # Increased by weight, reduced by tier
        self.equip_time = 0.1 * self.weight / math.sqrt(1 + 0.1 * self.tier)
        self.equip_time = triangle_roll(self.equip_time, 0.07)
        # Damage is constant, modified by weight and tier
        damage = round(self.weight**2 * math.sqrt(1+0.1*self.tier))
        self.damage_range = damage, damage
        self.redraw_loot()

    def activate(self, character, continuous_input):
        # Only activates if:
        # 1. Input is continuous AND was not interrupted since start
        # 2. Shield is static and input is first
        # 3. SHIELD BASH: instant full activation if character is running close to own max speed
        if not (
                (continuous_input and self.active_last_frame) or
                (not continuous_input and self.activation_offset == v())
        ):
            return

        if self.disabled and not character.ramming and self.reactivation_timer <= 0:
            return

        self.active_this_frame = True
        self.held_counter += FPS_TICK
        self.in_use = True
        self.speed_limit = self.character_specific["speed_limit"]

        # Player characters may activate shields instantly when running; also causes bash attack
        if self.can_bash(character) and not continuous_input:
            character.stamina *= 0.5

            self.held_counter = self.equip_time
            character.shielded = self

            bash_intensity = 1.5*character.speed.length()*(1+self.agility_modifier)
            bash_angle = -self.last_angle

            bash_vector = v()
            bash_vector.from_polar((bash_intensity, bash_angle))

            character.push(bash_vector, 0.5, 'bashing')
            self.inertia_vector = v(self.character_specific["x_component"], 0)
            self.activation_offset = v(
                character.body_coordinates["main_hand"][0] - character.body_coordinates["off_hand"][0],
                0
            )
            return

        # Instantly activate if grace period is applied:
        elif self.reactivation_timer > 0:
            self.disabled = False
            self.held_counter = self.equip_time
            character.shielded = self

        # Calculate activation vector if not already:
        elif self.held_counter < self.equip_time:

            # Activation is 70% of the way from off-hand to main_hand
            x_component = (character.body_coordinates["main_hand"][0] - character.body_coordinates["off_hand"][0])\
                / self.equip_time * 0.7
            self.inertia_vector = v(x_component, 0)
        else:
            character.shielded = self

        if not character.ramming:
            character.set_state('active', 0.2)

        lock_time = FPS_TICK if not character.ramming else 0.5
        # Lock self for 1 frame
        self.lock(lock_time, angle=0 if character.facing_right else 180, inertia=self.inertia_vector)
        # lock other weapons
        for slot in character.weapon_slots:

            if self == character.slots[slot]:
                continue

            weapon = character.slots[slot]
            if isinstance(weapon, Wielded):
                weapon.disabled = True
                if character.facing_right:
                    angle = weapon.default_angle
                else:
                    angle = math.copysign(180, weapon.default_angle) - weapon.default_angle
                weapon.lock(angle=angle, duration=lock_time)

    def on_equip(self, character):
        super(Shield, self).on_equip(character)
        self.character_specific['x_component'] = (character.body_coordinates["main_hand"][0] -
                                                  character.body_coordinates["off_hand"][0]) / self.equip_time * 0.7
        self.character_specific['pushback_resistance'] = (1 - self.stamina_drain) / (self.weight + character.weight)
        self.character_specific['speed_limit'] = 1/self.equip_time

    def hitbox(self):
        return []

    def draw(self, character, **kwargs):
        try:
            surface, rect = super().draw(character, **kwargs)
        except ValueError:
            # may return nothing; in this case, nothing is also returned
            return

        if not character.facing_right:
            surface = pygame.transform.flip(surface, False, True)

        # Blocking shields are colored
        if self.held_counter >= self.equip_time:
            surface = tint(surface, self.color or character.attacks_color)
        # Bash-ready shields are colored and display an arrow in front of the character
        elif self.can_bash(character):
            surface = tint(surface, self.color or character.attacks_color)

            # Make sure to reset frames
            self.trail_frames: list = [None] * int(FPS_TARGET * 0.03 + 1)
            self.frame_counter = 0

            arrow_v = v()
            arrow_v.from_polar((character.hitbox[0].width, -self.last_angle))
            arrow_position = character.position + arrow_v

            arrow_surface = pygame.transform.rotate(self.active_arrow, self.last_angle)
            arrow_rect = arrow_surface.get_rect(center=arrow_position)

            return surface, rect, [[arrow_surface, arrow_rect]]

        # Leave trails during shield bash:
        elif character.ramming:
            if self.frame_counter < 3:
                self.frame_counter += 1
            else:
                self.trail_frames.pop(0)
                trail = tint(surface, self.color or character.attacks_color)
                trail.set_alpha(127)
                self.trail_frames.append([trail, rect])
                self.frame_counter = 0

            return surface, rect, [trail for trail in self.trail_frames if trail]

        # Make sure to reset frames
        self.trail_frames: list = [None] * int(FPS_TARGET * 0.03 + 1)
        self.frame_counter = 0
        return surface, rect

    def block(self, character, damage, vector, weapon: Wielded = None, offender=None):

        # Determine how much stamina would a full block require
        character.stamina -= damage * self.stamina_drain

        block_failed = character.stamina < 0

        # Prevent protecting from back attacks
        if offender:
            block_failed = (character.position.x > offender.position.x) == character.facing_right or block_failed

        if block_failed:
            # Displace self by enemy weapon delta
            if weapon:
                self.activation_offset += weapon.tip_delta

            # Spawn a kicker and queue destruction if held by AI:
            self.queue_destroy = character.ai is not None
            self._kicker('DESTROYED!' if self.queue_destroy else 'BROKEN!', character)

            # Return full damage and force
            return vector, damage

        # Cause character movement by reduced force:
        # The more damage was blocked, the higher the pushback
        character.speed += vector * self.character_specific['pushback_resistance']
        blowback = -vector
        blowback.scale_to_length(self.weight)
        weapon.parry(
            owner=offender,
            opponent=character,
            other_weapon=self,
            calculated_impact=blowback
        )

        kicker_text = 'BLOCKED!'

        # Deal additional stamina damage to attacker:
        if offender:
            offender.stamina *= 0.5

        # If block is performed by AI, there is a chance to drop shield
        if offender and character.ai:

            chance = max(
                (damage - weapon.damage_range[0])/weapon.damage_range[1] * weapon.weight/self.weight,
                0.1
            )

            attempt = random.random()
            self.queue_destroy = chance > attempt
            if self.queue_destroy:
                kicker_text = 'DESTROYED!'

        # Spawn 'BLOCKED' kicker
        self._kicker(kicker_text, character)

        return v(), 0

    def _kicker(self, kicker_text, character):
        blocked_kicker = Kicker(
            position=v(character.position),
            damage_value=0,
            color=colors["crit_kicker"],
            override_string=kicker_text
        )
        self.particles.append(blocked_kicker)

    def portrait(self, rect: r, offset=BASE_SIZE*2, discolor=True):
        surface = s(rect.size, pygame.SRCALPHA)

        # Find horizontal scale to fill the rectangle:
        scale = 3*(rect.width-2*offset)/self.surface.get_rect().width
        portrait = pygame.transform.rotozoom(self.surface, 15, scale)
        if discolor:
            if self.durability > 0:
                color = c(colors["inventory_text"])
            else:
                color = c(colors["inventory_broken"])

            portrait = tint(portrait, color)
        new_width = portrait.get_width()

        surface.blit(portrait, portrait.get_rect(left=max(0, (rect.width - new_width)//2), top=offset*0.5))

        return surface

    def show_stats(self, compare_to=None):
        stats_dict: dict = super().show_stats(compare_to=compare_to)

        if compare_to is not None:
            comparison_dict = compare_to.show_stats()
        else:
            comparison_dict = dict()

        stats_dict["USE TIME"] = {
            "value": self.equip_time,
            "text": f'{self.equip_time:.2f}'
        }
        stats_dict["DAMAGE"]["text"] = f'{self.damage_range[0]}'  # remove damage spread

        if "USE TIME" in comparison_dict:
            stats_dict["USE TIME"]["evaluation"] = comparison_dict["USE TIME"]["value"] - self.equip_time

        return stats_dict

    def aim(self, hilt_placement, aiming_vector, character):
        # Tick down immunity:
        if self.internal_immunity > 0:
            self.internal_immunity -= FPS_TICK

        if not character.ramming and self.reactivation_timer > 0:
            self.reactivation_timer -= FPS_TICK

        self.active_last_frame = self.active_this_frame
        # If activation timer is completed, set character.shielded to True
        if self.held_counter >= self.equip_time:
            character.shielded = self
        if not self.active_this_frame:
            # If returned in place, allow to be active again:
            if self.activation_offset == v():
                self.in_use = False

            # Reset to place:
            self.held_counter = 0
            character.shielded = None

        super().aim(hilt_placement, aiming_vector, character)

        if not character.ramming:
            self.active_this_frame = False

    def deal_damage(self, vector=v(), victim=None, attacker=None):
        # Spawn dust clouds
        rect = self.surface.get_rect(center=self.hilt_v)
        for _ in range(random.randint(7, 9)):
            self.particles.append(DustCloud(rect))

        self.reactivation_timer = self._grace_period
        return self.damage_range[0]

    def can_bash(self, character):
        enough_energy = character.stamina >= character.max_stamina * 0.5
        going_forward = character.facing_right == (character.speed.x > 0)
        going_fast = abs(character.speed.x) >= character.max_speed * (1.2-self.agility_modifier)
        can_bash = character.ai is None and self.activation_offset == v()
        return all((enough_energy, going_fast, going_forward, can_bash))


class Swordbreaker(Dagger, OffHand):
    class_name = "Swordbreaker"
    stab_modifier = 1.7
    aim_drain_modifier = 0.0
    return_time = 0.2
    held_position = v(-55, 5)
    upside = [
        "Activate to dash and stab",
        "Held in forward position",
        "Activate after parrying to roll thorugh",
        "Restores stamina on hits and parries"
    ]

    def generate(self, size, tier=None):
        # Fill missing parts of self.builder on the go:
        self.builder["constructor"] = self.builder.get("constructor", {})
        self.builder["tier"] = self.builder.get("tier", tier)

        # Use this for calculations from now on
        tier = self.builder["tier"]

        self.builder["class"] = "Swordbreaker"

        # Create a blade:
        self.builder["constructor"]["blade"] = self.builder["constructor"].get("blade", {})
        self.builder["constructor"]["blade"]["str"] = self.builder["constructor"]["blade"].get(
            "str", random.choice(parts_dict['swordbreaker']['blades'])

        )
        self.builder["constructor"]["blade"]["material"] = self.builder["constructor"]["blade"].get(
            "material", Material.pick(['metal', 'precious'], roll_tier(tier))
        )

        # Create a hilt
        self.builder["constructor"]["hilt"] = self.builder["constructor"].get("hilt", {})
        self.builder["constructor"]["hilt"]["str"] = self.builder["constructor"]["hilt"].get(
            "str", random.choice(parts_dict['dagger']['hilts'])
        )

        def new_hilt_material():
            if random.random() > 0.7:  # 30% of the time, pick same material for hilt
                hm = Material.pick(['metal', 'wood', 'bone', 'precious'], roll_tier(tier))
            else:
                hm = self.builder["constructor"]["blade"]["material"]
            return hm

        self.builder["constructor"]["hilt"]["material"] = self.builder["constructor"]["hilt"].get(
            "material", new_hilt_material()
        )

        # Generate colors:
        self.builder["constructor"]['blade']["color"] = self.builder["constructor"]['blade'].get(
            "color", Material.registry[self.builder["constructor"]['blade']["material"]].generate()
        )

        def new_hilt_color():
            if 'painted' in set(self.builder["constructor"]['hilt'].get("tags", [])):
                return paint()

            # If parts share material, share color
            if self.builder["constructor"]['blade']["material"] == self.builder["constructor"]['hilt']["material"]:
                return self.builder["constructor"]['blade']["color"]

            # 10%, paint the hilt
            if Material.registry[self.builder["constructor"]['hilt']["material"]].physics in PAINTABLE and \
                    random.random() > 0.9:
                self.builder["constructor"]['hilt']['tags'] = ['painted']
                return paint()

            # Generate usual material color
            return Material.registry[self.builder["constructor"]['hilt']["material"]].generate()

        self.builder["constructor"]['hilt']["color"] = self.builder["constructor"]['hilt'].get(
            "color", new_hilt_color()
        )

        hilt_str = self.builder["constructor"]["hilt"]["str"]
        blade_str = self.builder["constructor"]["blade"]["str"]
        hilt_material = self.builder["constructor"]["hilt"]["color"]
        blade_material = self.builder["constructor"]["blade"]["color"]

        self.surface = ascii_draws(
            size,
            (
                (hilt_str, hilt_material),
                (blade_str, blade_material)
            )
        )

        # Hold between 1st and second hilt character -- offset exactly 1 character
        self.hilt = self.surface.get_width() / len(hilt_str + blade_str), self.surface.get_height() * 0.5

        # Dagger tip coordinate relative to hilt -- offset 1.25 character_positions
        self.length = self.surface.get_width() - self.hilt[0] * 1.25

        self.color = Material.registry[self.builder["constructor"]["blade"]["material"]].attacks_color

    def update_stats(self):
        super().update_stats()
        # Like Dagger, but damage is lower and roll_window is higher
        self.damage_range = int(self.damage_range[0] * 0.7), int(self.damage_range[1] * 0.8)
        self.roll_window = 1.5*self.roll_window
        self.redraw_loot()

    def aim(self, hilt_placement, aiming_vector, character):
        # Restore 5% max stamina per second if not draining it
        if self.stamina_ignore_timer > 0:
            if character.stamina < character.max_stamina:
                character.stamina += character.max_stamina * 0.05 * FPS_TICK
        super().aim(hilt_placement, aiming_vector, character)

    def deal_damage(self, vector=v(), victim=None, attacker=None):
        self.stamina_ignore_timer = min(self.stamina_ignore_timer, 0.6)
        return super(Swordbreaker, self).deal_damage(vector, victim, attacker)

    def parry(self, owner, opponent, other_weapon, calculated_impact=None):
        super(Swordbreaker, self).parry(owner, opponent, other_weapon, calculated_impact)
        self.stamina_ignore_timer = min(self.stamina_ignore_timer, 0.6)


class Katar(Pointed, OffHand):
    # class_name = "Katar"
    max_tilt = 85
    default_angle = 0
    stab_modifier = 1.8
    aim_drain_modifier = 0.0
    return_time = 0.2
    held_position = v(-15, 5)
    stab_dash_modifier = 0
    stab_cost = 0.25
    upside = [
        "Activate to stab and bleed enemy",
        "Hold activation to stab and immobilize enemy",
        "Restores stamina on hits and parries"
    ]
    offside = ["No swing attacks", "Can't parry"]
    hides_hand = True
    can_parry = False

    def __init__(self, *args, **kwargs):
        self.hidden_surface = None
        self.bleed = 0
        super(Katar, self).__init__(*args, **kwargs)

    def is_dangerous(self):
        return self.in_use

    def draw(self, character, _custom_surface=None):
        if _custom_surface:
            use_surface = _custom_surface
        elif self.kebab:
            use_surface = self.skewering_surface
        elif self.in_use:
            use_surface = self.surface
        else:
            use_surface = self.hidden_surface

        return Wielded.draw(
            self,
            character,
            _custom_surface=use_surface
        )

    def generate(self, size, tier=None):
        # Fill missing parts of self.builder on the go:
        self.builder["constructor"] = self.builder.get("constructor", {})
        self.builder["tier"] = self.builder.get("tier", tier)

        # Use this for calculations from now on
        tier = self.builder["tier"]

        self.builder["class"] = "Katar"

        # Create a blade:
        self.builder["constructor"]["blade"] = self.builder["constructor"].get("blade", {})
        self.builder["constructor"]["blade"]["str"] = self.builder["constructor"]["blade"].get(
            "str", random.choice(parts_dict['katar']['blades'])

        )
        self.builder["constructor"]["blade"]["material"] = self.builder["constructor"]["blade"].get(
            "material", Material.pick(['metal', 'precious', 'mineral'], roll_tier(tier))
        )

        # Create a guard
        self.builder["constructor"]["guard"] = self.builder["constructor"].get("guard", {})
        self.builder["constructor"]["guard"]["str"] = self.builder["constructor"]["guard"].get(
            "str", random.choice(parts_dict['katar']['guards'])
        )

        def new_guard_material():
            # Never use same material as blade
            picked_blade_material = self.builder["constructor"]["blade"]["material"]

            return Material.pick(
                ['metal', 'leather', 'bone', 'precious'],
                roll_tier(tier),
                lambda x:
                    x.name not in Material.collections['plateless_bone'] and
                    x != Material.registry[picked_blade_material]
            )

        self.builder["constructor"]["guard"]["material"] = self.builder["constructor"]["guard"].get(
            "material",
            new_guard_material()
        )

        # Generate colors:
        self.builder["constructor"]['blade']["color"] = self.builder["constructor"]['blade'].get(
            "color", Material.registry[self.builder["constructor"]['blade']["material"]].generate()
        )

        def new_guard_color():
            if 'painted' in set(self.builder["constructor"]['guard'].get("tags", [])):
                return paint()

            # 50%, paint the handle
            if Material.registry[self.builder["constructor"]['guard']["material"]].physics in PAINTABLE and \
                    random.random() > 0.5:
                self.builder["constructor"]['guard']['tags'] = ['painted']
                return paint()

            # Generate usual material color
            return Material.registry[self.builder["constructor"]['guard']["material"]].generate()

        self.builder["constructor"]['guard']["color"] = self.builder["constructor"]['guard'].get(
            "color", new_guard_color()
        )

        handle_str = self.builder["constructor"]["guard"]["str"]
        blade_str = self.builder["constructor"]["blade"]["str"]
        handle_material = self.builder["constructor"]["guard"]["color"]
        blade_material = self.builder["constructor"]["blade"]["color"]

        self.surface = ascii_draws(
            size,
            (
                (handle_str, handle_material),
                (blade_str, blade_material)
            )
        )
        self.skewering_surface = ascii_draws(
            size,
            (
                (handle_str, handle_material),
                (blade_str[:-1] + ' ', blade_material)
            )
        )
        self.hidden_surface = ascii_draws(
            size,
            (
                (handle_str, handle_material),
                (blade_str[1]+' ', blade_material)
            )
        )

        # Hold between 1st and second handle character -- offset exactly 1 character
        self.hilt = self.surface.get_width() / len(handle_str + blade_str), self.surface.get_height() * 0.5

        # Dagger tip coordinate relative to handle -- offset 1.25 character_positions
        self.length = self.surface.get_width() - self.hilt[0] * 1.25

        self.color = Material.registry[self.builder["constructor"]["blade"]["material"]].attacks_color

    def update_stats(self):
        guard = Material.registry[self.builder["constructor"]["guard"]["material"]]
        blade = Material.registry[self.builder["constructor"]["blade"]["material"]]

        # Generate stats according to Material.registry
        self.weight = 1.5*guard.weight + 2 * blade.weight
        self.tier = int((guard.tier+blade.tier)*0.5)

        # reduced for blade weight, increased for hilt tier
        self.agility_modifier = math.sqrt((10.0 + guard.tier) / (1.6 * (1 + blade.weight)))
        # Increased for dagger total weight, reduced for blade tier and hilt weight (1.3-1.6)
        # SQRT to bring closer to 1.0
        self.stamina_drain = math.sqrt(self.weight / ((2 + blade.tier) * math.sqrt(guard.weight)))

        # Calculate damage range depending on weight and tier:
        min_damage = int((33 + 0.5 * self.weight) * 1.08 ** (self.tier - 1))
        max_damage = int(min_damage * 1.2)
        self.damage_range = min_damage, max_damage

        # Depends on total weight and heavily on blade tier
        self.bleed = triangle_roll(0.01 * (self.weight + blade.tier**2), 0.07)

        self.redraw_loot()

    def show_stats(self, compare_to=None):
        stats_dict: dict = super().show_stats(compare_to=compare_to)

        if compare_to is not None:
            comparison_dict = compare_to.show_stats()
        else:
            comparison_dict = dict()

        stats_dict["BLEED"] = {
            "value": self.bleed,
            "text": f'{100*self.bleed:.1f}%/s'
        }

        if "BLEED" in comparison_dict:
            stats_dict["BLEED"]["evaluation"] = self.bleed - comparison_dict["BLEED"]["value"]

        return stats_dict

    def aim(self, hilt_placement, aiming_vector, character):
        # Restore 5% max stamina per second if not draining it
        if self.stamina_ignore_timer > 0:
            if character.stamina < character.max_stamina:
                character.stamina += character.max_stamina * 0.05 * FPS_TICK
        return Wielded.aim(self, hilt_placement, aiming_vector, character)
