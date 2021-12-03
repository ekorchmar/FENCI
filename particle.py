# todo:

from base_class import *


class Kicker(Particle):
    shakeable = True
    clampable = True

    """Display oscilating floating damage number when character is hit"""
    def __init__(
            self,
            position,
            damage_value,
            color,
            base_speed=POKE_THRESHOLD / 2,
            lifetime=REMAINS_SCREENTIME / 1.5,
            weapon=None,
            critcolor=None,
            override_string=None,
            oscillate=True,
            size=BASE_SIZE // 1.5
    ):

        if override_string:
            damage_string = override_string
        else:
            damage_string = "{:.0f}".format(damage_value)

            if weapon:
                # Color crits
                if damage_value == weapon.damage_range[1]:
                    damage_string = str(weapon.damage_range[1]) + '!'
                    color = critcolor or color
                # Higher damage flies faster
                try:
                    progression = (damage_value-weapon.damage_range[0])/(weapon.damage_range[1]-weapon.damage_range[0])
                    base_speed = lerp((0.5*base_speed, base_speed), progression)
                except ZeroDivisionError:
                    pass

        self.surface = ascii_draw(int(size), damage_string, color)
        self.position = v(position[:])
        self.max_lifetime = lifetime
        self.lifetime = lifetime
        self.speed = v(0, -base_speed)
        self.cache = None
        self.oscillate = oscillate

    def draw(self, pause=False):
        if pause and self.cache:
            return self.cache

        self.lifetime -= FPS_TICK
        self.position += self.speed
        if self.oscillate:
            oscillation_x = BASE_SIZE * math.sin(pygame.time.get_ticks() * 0.5 * FPS_TICK) * 0.4
            center_v = self.position + v(oscillation_x, 0)
        else:
            center_v = self.position

        # Clamping this way does not work due to screen scrolling. On the other hand,
        # there is no need to clamp it with bigger arena size
        # rect = self.surface.get_rect(center=center_v).clamp(0, 0, *WINDOW_SIZE)
        rect = self.surface.get_rect(center=center_v)

        transparency = int(255*self.lifetime / self.max_lifetime)
        transparent_surface = self.surface.copy()
        transparent_surface.set_alpha(transparency)

        self.cache = transparent_surface, rect
        return transparent_surface, rect


class Remains:
    shakeable = True

    def __init__(self, blitting_list, persistence, bounding_box, particle_dump: list = None):
        """Takes list of lists of three: surface, drawing rect, initial movement vector"""
        self.bounding_box = bounding_box

        # Stop all free-falling objects randomly in first seconds of animation
        self.blitting_list = []
        for triple in blitting_list:
            if not triple:  # Some things may return nothing
                continue
            quintuple = [
                *triple,
                0.5 + random.uniform(0, 2),
                REMAINS_SCREENTIME * persistence if persistence != 0 else None
            ]
            self.blitting_list.append(quintuple)
        self.lifetime = len(self.blitting_list)
        self.cache = None

        self.particle_dump = particle_dump

    def draw(self, pause=False):
        if pause and self.cache:
            return self.cache

        output = []
        new_list = []

        # Unpack:
        for surface, rect, speed_v, time, decay_timer in self.blitting_list:

            # Modify:
            time -= FPS_TICK
            if time <= 0:
                # Stop moving and add dust particles
                if speed_v.y > 0 and self.particle_dump is not None:
                    for _ in range(random.randint(3, 4)):
                        self.particle_dump.append(DustCloud(rect, max_opacity=127))

                speed_v = v()
            else:
                speed_v += FFA
                rect.move_ip(speed_v)

                # If rect hits bounding box, bounce
                boundaries = (self.bounding_box.left, self.bounding_box.right),\
                             (self.bounding_box.top, self.bounding_box.bottom)
                center_v = v(self.bounding_box.center)

                for coordinate in [0, 1]:
                    if not boundaries[coordinate][0] < rect.center[coordinate] < boundaries[coordinate][1]:
                        to_center = center_v - v(rect.center)
                        to_center.scale_to_length(speed_v.length() * 0.5)
                        to_center.y *= 0.6

                        speed_v = to_center

            if speed_v == v() and decay_timer is not None:
                decay_timer -= FPS_TICK

            transparency = int(127 * (decay_timer if decay_timer is not None else 1) / REMAINS_SCREENTIME)
            transparent_surface = surface.copy()
            transparent_surface.set_alpha(transparency)

            # Log into output:
            output.append((transparent_surface, rect))

            # Repack:
            if decay_timer is None or decay_timer > 0:
                new_list.append([surface, rect, speed_v, time, decay_timer])

        self.blitting_list = new_list
        self.lifetime = len(self.blitting_list)

        self.cache = output
        return output


class Spark(Particle):
    shakeable = True

    def __init__(
            self,
            position,
            vector: v(),
            weapon=None,
            attack_color=None,
            lifetime=REMAINS_SCREENTIME/8,
            size=0.75,
            angle_spread=(-15, 15)
    ):

        # Randomize Spark lifetime:
        self.lifetime = lifetime * random.uniform(0.9, 1.1)
        self.angle = random.randint(0, 45)

        # Create own surface
        shape = random.choice(['+', '*', '★', '☆', '•', '○'])
        # Color is 66% chance attack color (if specified), weapon's hitting part color otherwise
        if weapon is None or (attack_color and random.random() > 0.34):
            color = attack_color
        else:
            # Hitting surface should be more likely to be used for spark color
            weapon_parts = list(weapon.builder["constructor"].keys())
            weapon_part_weights = [
                (3 if part == weapon.hitting_surface else 1) for part in weapon_parts
            ]
            crumbling_part = random.choices(weapon_parts, weapon_part_weights)[0]

            color = weapon.builder["constructor"][crumbling_part]["color"]
            # Make color lighter
            color = c(color)
            hsl_list = [*color.hsla]
            hsl_list[2] = 40 + hsl_list[2] * random.uniform(0.3, 0.6)
            color.hsla = hsl_list

        self.surface = ascii_draw(int(size*BASE_SIZE), shape, color)
        self.position = v(position[:])

        # Randomize movement:
        self.speed = vector*random.triangular(0.5, 1)
        self.speed.rotate_ip(random.uniform(*angle_spread))
        self.angular_speed = random.uniform(-MAX_SPEED/2, +MAX_SPEED/2)

        self.cache = None

    def draw(self, pause=False):
        if pause and self.cache:
            return self.cache

        self.lifetime -= FPS_TICK
        self.position += self.speed
        self.angle += self.angular_speed
        draw = rot_center(self.surface, self.angle, self.position)

        self.cache = draw
        return draw


class Droplet(Particle):
    shakeable = True

    def __init__(self, position, character, lifetime=REMAINS_SCREENTIME/4, size=0.5, spawn_delay=None):
        # If blood is disabled, instantly despawn any droplets
        if OPTIONS["red_blood"] == 2:
            lifetime = -1

        if spawn_delay is None:
            spawn_delay = random.uniform(0, 0.6)

        # If lifetime > max_lifetime, particle does not appear yet
        self.lifetime = lifetime * random.uniform(0.9, 1.1)
        self.max_lifetime = lifetime

        if character.hp > 0:
            self.lifetime += spawn_delay

        shape = random.choice(['♥', '❤', '♠'])

        self.surface = ascii_draw(
            int(size*BASE_SIZE),
            shape,
            c(204, 0, 0) if OPTIONS["red_blood"] == 0 else character.blood
        )

        # If character is alive, tether own position to the character
        self.character = character
        if character.hp > 0:
            self.position = v(position) - v(self.character.position)
        else:
            self.position = v(position)

        r_phi = SWING_THRESHOLD*0.2, random.uniform(-180, 180)
        self.speed = v()
        self.speed.from_polar(r_phi)

        self.cache = None

    def draw(self, pause=False):
        if self.cache and pause:
            return self.cache

        self.lifetime -= FPS_TICK
        # May be not spawned yet:
        if self.lifetime > self.max_lifetime:
            return None

        self.position += self.speed
        self.speed += FFA
        decay = self.lifetime/self.max_lifetime

        size_modifier = 1 + 1.5 * (1-decay)
        transparency = int(255*decay)

        # If character is alive, tether own position to the character
        if self.character.hp > 0:
            center_v = self.position + v(self.character.position)
        else:
            center_v = self.position

        surface = pygame.transform.rotozoom(self.surface, 0, size_modifier)
        surface.set_alpha(transparency)
        rect = surface.get_rect(center=center_v)

        self.cache = surface, rect
        return surface, rect


class AttackWarning(Particle):
    shakeable = True
    clampable = True

    def __init__(
            self,
            relative_position,
            character,
            lifetime=REMAINS_SCREENTIME*0.5,
            text='<!>',
            size=BASE_SIZE*2,
            custom_color=None,
            monitor=None
    ):
        self.surface = ascii_draw(size, text, custom_color or pygame.color.Color(character.attacks_color))
        self.lifetime = self.max_lifetime = lifetime
        self.character = character
        self.position = relative_position
        self.cache = None
        self.monitor = monitor or (lambda: True)

    def draw(self, pause=False):
        if self.cache and pause:
            return self.cache

        self.lifetime = self.lifetime - FPS_TICK if self.monitor() else -1

        # Start almost transparent, full color before strike
        transparency = 255 - int(200 * self.lifetime/self.max_lifetime)
        surface = self.surface.copy()
        surface.set_alpha(transparency)
        placement = self.character.position + self.position
        rect = surface.get_rect(center=placement)

        self.cache = surface, rect
        return surface, rect


class Banner(Particle):
    shakeable = False
    _max_angle = 10
    _min_angle = 15

    def __init__(
            self,
            text,
            size,
            position,
            color,
            lifetime=REMAINS_SCREENTIME,
            animation='fade',
            max_width=WINDOW_SIZE[0],
            tick_down=True,
            anchor='center',
            background=False,
            forced_tickdown=None,
            **animation_options
    ):
        self.text = text
        drawn_text = ascii_draw_cascaded(size, text, color, max_width=max_width)
        if background:
            self.surface = s(drawn_text.get_size(), pygame.SRCALPHA)
            self.surface.fill(colors["loot_card"])
            frame_surface(self.surface, colors["inventory_text"])
            self.surface.blit(drawn_text, (0, 0))
        else:
            self.surface = drawn_text
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.forced_tickdown = forced_tickdown
        self.tick_down = tick_down

        # Positioning and orientation
        self.anchor = anchor
        self.position = position

        if animation not in {None, 'fade', 'slide', 'simple', 'grow', 'settle'}:
            raise KeyError("Invalid animation")
        else:
            self.animation = animation

        # Process animation options
        self.animation_duration = animation_options.get("animation_duration", 1.0)
        self.scale_factor = animation_options.get("scale_factor", 5)
        self.cache = None

    def draw(self, pause=None):

        if pause is not None:
            self.tick_down = self.forced_tickdown if self.forced_tickdown is not None else not pause

        if self.tick_down or self.max_lifetime - self.lifetime < self.animation_duration:
            self.lifetime -= FPS_TICK
        elif self.cache:
            return self.cache

        surface = self.surface.copy()

        positioning = {self.anchor: self.position[:]}
        rect = surface.get_rect(**positioning)
        timer = (self.max_lifetime - self.lifetime)

        if self.animation == 'fade':
            transparency = 255
            scale = 1.0

            if timer <= self.animation_duration:
                transparency = int(255*timer/self.animation_duration)
                scale = 1 + (self.scale_factor - 1) * (1 - timer/self.animation_duration)
            elif self.lifetime <= self.animation_duration:
                transparency = int(255*self.lifetime/self.animation_duration)
                scale = 1 + (self.scale_factor - 1) * (1 - self.lifetime/self.animation_duration)

            if transparency != 255:
                surface.set_alpha(transparency)

            if scale != 1.0:
                surface = pygame.transform.smoothscale(
                    surface,
                    (int(surface.get_width() * scale), int(surface.get_height()*scale))
                )

            rect = surface.get_rect(**positioning)

        elif self.animation == 'slide':
            offset_start_x = WINDOW_SIZE[0] + self.surface.get_width() // 2 - self.position[0]
            offset_end_x = -self.surface.get_width() // 2 - self.position[0]

            if timer <= self.animation_duration:
                progress = timer/self.animation_duration
                state = 'appear'
            elif self.lifetime <= self.animation_duration:
                progress = self.lifetime/self.animation_duration
                state = 'leave'
            else:
                state = 'static'
                progress = 0

            if state == 'appear':
                rect.move_ip(offset_start_x*(1-progress), 0)
            elif state == 'leave':
                rect.move_ip(offset_end_x*(1-progress), 0)

        elif self.animation == 'simple':
            transparency = 255

            if timer <= self.animation_duration:
                transparency = int(255*timer/self.animation_duration)
            elif self.lifetime <= self.animation_duration:
                transparency = int(255*self.lifetime/self.animation_duration)

            if transparency != 255:
                surface.set_alpha(transparency)

            rect = surface.get_rect(**positioning)

        elif self.animation == 'grow':
            scale = 1.0
            transparency = 255

            if timer <= self.animation_duration:
                scale = timer/self.animation_duration
            elif self.lifetime <= self.animation_duration:
                transparency = int(255*self.lifetime/self.animation_duration)
                scale = 1 + (self.scale_factor - 1) * (1 - self.lifetime/self.animation_duration)

            if transparency != 255:
                surface.set_alpha(transparency)

            if scale != 1.0:
                surface = pygame.transform.smoothscale(
                    surface,
                    (int(surface.get_width() * scale), int(surface.get_height()*scale))
                )

            rect = surface.get_rect(**positioning)

        elif self.animation == 'settle':
            if timer <= self.animation_duration:
                progress = 1-timer/self.animation_duration

                # This is the way to randomize starting angle, but to keep it constant each iteration
                max_angle = self._max_angle * 0.01 * (id(self) % 100 - 50)
                max_angle += math.copysign(self._min_angle, max_angle)

                surface, rect = rot_center(
                    surface,
                    max_angle * progress,
                    rect.center
                )

        self.cache = surface, rect
        return surface, rect


class Stunned(Particle):
    shakeable = True

    def __init__(
            self,
            character,
            relative_position=None,
            text='@',
            size=BASE_SIZE*3//2
    ):
        self.surface = ascii_draw(size, text, c(colors["stunned"]))
        self.lifetime = 1
        self.character = character
        if relative_position is None:
            side = -1 if self.character.facing_right else 1
            self.position = self.character.body_coordinates["bars"] + v(2*side*BASE_SIZE, 0)
        else:
            self.position = relative_position
        self.cache = None

    def draw(self, pause=False):
        if pause and self.cache:
            return self.cache

        # Despawn if state is changed:
        if self.character.state not in DISABLED or self.character.hp <= 0:
            self.lifetime = -1

        # Slowly rotate
        surface = pygame.transform.rotate(self.surface, pygame.time.get_ticks() * 0.1)
        placement = self.character.position + self.position
        rect = surface.get_rect(center=placement)

        self.cache = surface, rect
        return surface, rect


class SpeechBubble(Particle):
    shakeable = True
    clampable = True

    def __init__(
        self,
        relative_position,
        color,
        character,
        text,
        box,
        lifetime: float = REMAINS_SCREENTIME * 0.5,
        size: int = BASE_SIZE * 2 // 3
    ):
        decorated_rows = [[row, color] for row in frame_text([text]).splitlines()]
        self.surface = ascii_draw_rows(size, decorated_rows)
        self.lifetime = self.max_lifetime = lifetime
        self.character = character
        self.position = relative_position
        self.cache = None
        self.box = box

        # Add initial shake
        self.shaker = Shaker()
        self.shaker.add_shake(character.size/BASE_SIZE)

    def draw(self, pause=False):
        if self.cache and pause:
            return self.cache

        self.lifetime -= FPS_TICK

        # Start transparent, full color, than transparent again
        transparency = lerp((200, 255), math.sin(math.pi * self.lifetime/self.max_lifetime))
        surface = self.surface.copy()
        surface.set_alpha(transparency)
        placement = self.character.position + self.position + self.shaker.get_current_v()
        rect = surface.get_rect(center=placement).clamp(self.box)

        self.cache = surface, rect
        return surface, rect


class DustCloud(Particle):
    shakeable = True

    def __init__(self, spawn_rect: r, color=c(colors["dust"]), max_size=BASE_SIZE*2, lifetime=0.5, max_opacity=200):
        self.surface = ascii_draw(max_size, "☁", color)
        self.max_lifetime = self.lifetime = lifetime
        self.position = v(
            spawn_rect.left + random.uniform(0, spawn_rect.width),
            spawn_rect.top + random.uniform(0, spawn_rect.height)
        )
        self.speed = v()
        self.cache = None
        self.max_opacity = max_opacity

    def draw(self, pause=False):
        if pause and self.cache:
            return self.cache

        self.lifetime -= FPS_TICK

        self.position += self.speed
        self.speed -= FFA
        decay = 1-self.lifetime/self.max_lifetime
        surface = pygame.transform.rotozoom(self.surface, 0, decay)
        surface.set_alpha(self.max_opacity*(1-decay))
        rect = surface.get_rect(center=self.position)

        self.cache = surface, rect
        return surface, rect


class MouseHint(Particle):
    shakeable = False

    def __init__(
            self,
            relative_position,
            color,
            lifetime=REMAINS_SCREENTIME*0.5,
            text='<ACTION>',
            size=BASE_SIZE,
            monitor=None
    ):
        decorated_rows = [[row, color] for row in frame_text([text], style='┏━┓┗┛┃').splitlines()]
        self.surface = ascii_draw_rows(size, decorated_rows)

        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.position = relative_position
        self.cache = None
        self.monitor = monitor or (lambda: True)

    def draw(self, pause=False):
        if self.cache and pause:
            return self.cache

        self.lifetime = self.lifetime - FPS_TICK if self.monitor() else -1

        # Start full color transparent, transparent disappearance
        transparency = int(lerp((200, 255), self.lifetime/self.max_lifetime))
        surface = self.surface.copy()
        surface.set_alpha(transparency)
        placement = v(pygame.mouse.get_pos()) + self.position
        rect = surface.get_rect(center=placement)

        self.cache = surface, rect
        return surface, rect


class CountDown(Particle):
    shakeable = False

    def __init__(
            self,
            action,
            parameters,
            color,
            position,
            total_duration=2.7,
            count_down_from=3,
            text_size=BASE_SIZE*2,
            go_text=None,
            ignore_pause=True
    ):
        # Remember what to execute:
        self.lifetime = total_duration
        self.action = action
        self.parameters = parameters

        # May ignore pause:
        self.ignore_pause = ignore_pause
        self.cache = None

        # Calculate lifetime and content of each popup:
        total_spawns = count_down_from if go_text is None else count_down_from + 1
        time_per_banner = total_duration / total_spawns
        banner_texts = list(range(1, count_down_from+1))
        banner_texts.reverse()
        if go_text is not None:
            banner_texts += [go_text]

        # Form banner particles:
        self.banner_particles = [
            Banner(
                text=f' {str(text)} ',
                size=text_size,
                position=position,
                color=color,
                lifetime=time_per_banner,
                animation_duration=time_per_banner*0.33,
                background=True,
                animation='grow'
            )
            for text in banner_texts
        ]

        # Play first sound:
        play_sound('beep1', 1)

    def draw(self, pause=False):
        if self.cache and pause and not self.ignore_pause:
            return self.cache

        self.lifetime -= FPS_TICK

        # Perform action if over:
        if self.lifetime < 0:
            self.action(**self.parameters)
            return self.cache

        # Pop first banner in list, if it ran out
        if self.banner_particles[0].lifetime < 0:
            self.banner_particles.pop(0)
            play_sound('beep1', 1)
            if not self.banner_particles:
                play_sound('beep2', 1)

        # Draw (new) first banner:
        self.cache = self.banner_particles[0].draw()
        return self.cache


class LootOverlayHelp:
    shakeable = False

    def __init__(self, size=BASE_SIZE*3//4):
        # Get text particles
        self.particles = [
            MouseHint(
                v(0, -BASE_SIZE * 2),
                colors["inventory_title"],
                lifetime=REMAINS_SCREENTIME*0.5,
                text=string["overlay_hint"]["top"],
                size=size,
                monitor=None
            ),
            MouseHint(
                v(-BASE_SIZE * 3, 0),
                colors["inventory_title"],
                lifetime=REMAINS_SCREENTIME * 0.5,
                text=string["overlay_hint"]["left"],
                size=size,
                monitor=None
            ),
            MouseHint(
                v(BASE_SIZE * 3, 0),
                colors["inventory_title"],
                lifetime=REMAINS_SCREENTIME * 0.5,
                text=string["overlay_hint"]["right"],
                size=size,
                monitor=None
            )
        ]

    def draw(self):
        return [hint.draw(pause=False) for hint in self.particles]


class ComboCounter(Particle):
    shakeable = False
    _max_intensity = BASE_SIZE // 4
    _max_shake = 20

    def __init__(self, scene, position: v, font_size: int = BASE_SIZE*3//2):
        self.current_banner = None
        self.counter = 0
        self.lifetime = 1

        # Shake:
        self.shaker = Shaker(fading=False, max_shake=self._max_intensity)
        self.shake_v = v()

        # Banner options:
        self.position = position
        self.font_size = font_size

        # Plug to return if not needed:
        self.empty = s((0, 0)), r((0, 0, 0, 0))

        # Awareness of scene:
        self.scene = scene

    def increment(self):
        intensity = min(1.0, self.counter/self._max_shake)
        self.counter += 1
        self.shaker.reset()
        self.shaker.add_shake(intensity)
        banner_color = c(colors["lightning"]).lerp(c(colors["crit_kicker"]), intensity)
        self.current_banner = Banner(
            text=f"x{self.counter}",
            size=self.font_size,
            position=self.position,
            color=banner_color,
            lifetime=20,
            animation_duration=3,
            animation='settle',
            tick_down=False
        )

    def reset(self):
        if self.current_banner is not None:
            self.current_banner.animation = 'simple'
            self.current_banner.animation_time = 0.7
            self.current_banner.lifetime = 0.7
            self.current_banner.tick_down = True
        self.counter = 0

    def draw(self, pause=False):
        if self.current_banner is None:
            return self.empty

        if self.current_banner.lifetime < 0:
            self.current_banner = None
            return self.empty

        if not pause:
            self.shake_v = self.shaker.get_current_v()

        # Move banner to shaken position:
        self.current_banner.position = v(self.position + self.shake_v)
        surface, rect = self.current_banner.draw()

        return surface, rect


class EnemyDirection(Particle):
    shakeable = False
    clampable = True

    def __init__(self, player: Character, characters: list, size=BASE_SIZE*3//2):
        self.surface = ascii_draw(size, '▶', colors['lightning'])

        self.lifetime = 1
        self.player = player
        self.enemy = None
        self.distance2 = 0
        # Find the closest enemy to character
        self.find_closest_enemy(characters)

    def _set_enemy(self, enemy: Character):
        self.enemy = enemy
        self.distance2 = (self.player.position - enemy.position).length_squared()

    def find_closest_enemy(self, characters: list):
        # Reset if enemy is dead:
        if self.enemy not in characters:
            self.enemy = None
            self.distance2 = 0

        def enemy_filter(enemy):
            return (
                enemy.collision_group != self.player.collision_group and
                enemy.position and
                enemy.ai.target is self.player
            )

        for char in filter(enemy_filter, characters):
            if self.distance2 == 0 or (self.player.position - char.position).length_squared() < self.distance2:
                self._set_enemy(char)

    def draw(self, pause=False):
        if self.player.sees_enemies or self.enemy is None:
            return

        direction_angle = (self.enemy.position - self.player.position).as_polar()[1]
        surface = pygame.transform.rotozoom(self.surface, -direction_angle, 1)
        surface.set_alpha(int(127 + 127 * math.sin(pygame.time.get_ticks() * 0.02)))

        # Rely on scene clamping to reposition own sprite to the edge
        return surface, surface.get_rect(center=self.enemy.position)
