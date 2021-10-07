# todo:
#   banner background

from base_class import *


class Kicker(Particle):
    """Display oscilating floating damage number when character is hit"""
    def __init__(
            self,
            position,
            damage_value,
            color,
            base_speed=SWING_THRESHOLD / 4,
            lifetime=REMAINS_SCREENTIME / 1.5,
            weapon=None,
            critcolor=None
    ):

        damage_string = "{:.0f}".format(damage_value)

        if weapon:
            if damage_value == 0:
                damage_string = 'BLOCKED'
                color = critcolor
            elif damage_value == weapon.damage_range[1] != weapon.damage_range[0]:
                damage_string = str(weapon.damage_range[1]) + '!'
                color = critcolor or color
            # Higher damage flies faster
            try:
                progression = (damage_value - weapon.damage_range[0])/(weapon.damage_range[1]-weapon.damage_range[0])
                base_speed = lerp((0.5*base_speed, base_speed), progression)
            except ZeroDivisionError:
                pass

        self.surface = ascii_draw(int(BASE_SIZE // 1.5), damage_string, color)
        self.position = position
        self.max_lifetime = lifetime
        self.lifetime = lifetime
        self.speed = v(0, -base_speed)
        self.cache = None

    def draw(self, pause=False):
        if pause and self.cache:
            return self.cache

        self.lifetime -= FPS_TICK
        self.position += self.speed
        oscillation_x = BASE_SIZE * math.sin(pygame.time.get_ticks() * 0.5 * FPS_TICK) * 0.4
        center = self.position + v(oscillation_x, 0)
        rect = self.surface.get_rect(center=center)

        transparency = int(255*self.lifetime / self.max_lifetime)
        transparent_surface = self.surface.copy()
        transparent_surface.set_alpha(transparency)

        self.cache = transparent_surface, rect
        return transparent_surface, rect


class Remains:
    def __init__(self, blitting_list, bounding_box, particle_dump: list = None):
        """Takes list of lists of three: surface, drawing rect, initial movement vector"""
        self.bounding_box = bounding_box

        # Stop all free falling objects randomly in first seconds of animation
        self.blitting_list = []
        for triple in blitting_list:
            if not triple:  # Some things may return nothing
                continue
            quintuple = [*triple, 0.5 + random.uniform(0, 2), REMAINS_SCREENTIME]
            self.blitting_list.append(quintuple)
        self.lifetime = len(self.blitting_list)
        self.cache = None

        self.particle_dump = particle_dump

    def draw(self, pause=False):
        if pause and self.cache:
            return self.cache

        output = []
        new_list = []

        for quintuple in self.blitting_list:
            # Unpack:
            surface, rect, speed_v, time, decay_timer = quintuple

            # Modify:
            time -= FPS_TICK
            if time <= 0:
                # Stop moving and dust particles
                if speed_v.y > 0 and self.particle_dump is not None:
                    for _ in range(random.randint(3, 4)):
                        self.particle_dump.append(DustCloud(rect.center, max_opacity=127))

                speed_v = v()
            else:
                speed_v += FFA
                rect.move_ip(speed_v)

                # If rect hits bounding box, bounce
                boundaries = (self.bounding_box.left, self.bounding_box.right),\
                             (self.bounding_box.top, self.bounding_box.bottom)
                center = self.bounding_box.center

                for coordinate in [0, 1]:
                    if not boundaries[coordinate][0] < rect.center[coordinate] < boundaries[coordinate][1]:
                        to_center = v(center) - v(rect.center)
                        to_center.scale_to_length(speed_v.length() * 0.5)
                        to_center.y *= 0.6

                        speed_v = to_center

            if speed_v == v():
                decay_timer -= FPS_TICK

            transparency = int(127 * decay_timer / REMAINS_SCREENTIME)
            transparent_surface = surface.copy()
            transparent_surface.set_alpha(transparency)

            # Log into output:
            output.append((transparent_surface, rect))

            # Repack:
            if decay_timer > 0:
                new_list.append([surface, rect, speed_v, time, decay_timer])

        self.blitting_list = new_list
        self.lifetime = len(self.blitting_list)

        self.cache = output
        return output


class Spark(Particle):
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
        string = random.choice(['+', '*', '★', '☆', '•', '○'])
        # Color is 66% chance attack color (if specified), weapon's hitting part color otherwise
        if weapon is None or (attack_color and random.random() > 0.34):
            color = attack_color
        else:
            color = weapon.builder["constructor"][weapon.hitting_surface]["color"]
            # Make color lighter
            color = c(color)
            hsl_list = [*color.hsla]
            hsl_list[2] = 40 + hsl_list[2] * 0.6
            color.hsla = hsl_list

        self.surface = ascii_draw(int(size*BASE_SIZE), string, color)
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
    def __init__(self, position, character, lifetime=REMAINS_SCREENTIME/4, size=0.5, spawn_delay=None):
        if spawn_delay is None:
            spawn_delay = random.uniform(0, 0.6)

        # If lifetime > max_lifetime, particle does not appear yet
        self.lifetime = lifetime * random.uniform(0.9, 1.1)
        self.max_lifetime = lifetime

        if character.hp > 0:
            self.lifetime += spawn_delay

        string = random.choice(['♥', '❤', '♠'])

        self.surface = ascii_draw(int(size*BASE_SIZE), string, character.blood)

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
            center = self.position+v(self.character.position)
        else:
            center = self.position

        surface = pygame.transform.rotozoom(self.surface, 0, size_modifier)
        surface.set_alpha(transparency)
        rect = surface.get_rect(center=center)

        self.cache = surface, rect
        return surface, rect


class AttackWarning(Particle):

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
        self.monitor = monitor or self._monitor_decoy

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
            **animation_options
    ):
        self.text = text
        self.surface = ascii_draw_cascaded(size, text, color, max_width=max_width)
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.tick_down = tick_down
        self.position = position

        if animation not in {None, 'fade', 'slide'}:
            raise KeyError("Invalid animation")
        else:
            self.animation = animation

        # Process animation options
        self.animation_duration = animation_options.get("animation_duration", 1.0)
        self.scale_factor = animation_options.get("scale_factor", 5)
        self.cache = None

    def draw(self, pause=False):
        self.tick_down = not pause
        if self.tick_down or self.lifetime < self.animation_duration:
            self.lifetime -= FPS_TICK
        elif self.cache:
            return self.cache

        surface = self.surface.copy()
        rect = surface.get_rect(center=self.position[:])
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

            rect = surface.get_rect(center=self.position)

        if self.animation == 'slide':
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

        self.cache = surface, rect
        return surface, rect


class Stunned(Particle):
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
    def __init__(
        self,
        relative_position,
        color,
        character,
        text,
        lifetime: float = REMAINS_SCREENTIME * 0.5,
        size: int = BASE_SIZE // 2
    ):
        decorated_rows = [[row, color] for row in frame_text([text]).splitlines()]
        self.surface = ascii_draw_rows(size, decorated_rows)
        self.lifetime = self.max_lifetime = lifetime
        self.character = character
        self.position = relative_position
        self.cache = None

    def draw(self, pause=False):
        if self.cache and pause:
            return self.cache

        self.lifetime -= FPS_TICK

        # Start transparent, full color before strike, than transparent again
        transparency = lerp((200, 255), math.sin(math.pi * self.lifetime/self.max_lifetime))
        surface = self.surface.copy()
        surface.set_alpha(transparency)
        placement = self.character.position + self.position
        rect = surface.get_rect(center=placement)

        self.cache = surface, rect
        return surface, rect


class DustCloud(Particle):
    def __init__(self, position, color=c(colors["dust"]), max_size=BASE_SIZE*2, lifetime=0.5, max_opacity=200):
        self.surface = ascii_draw(max_size, "☁", color)
        self.max_lifetime = self.lifetime = lifetime
        random_offset = v(random.uniform(-BASE_SIZE/2, BASE_SIZE/2), random.uniform(-BASE_SIZE/2, BASE_SIZE/2))
        self.position = v(position[:]) + random_offset
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
        self.monitor = monitor or self._monitor_decoy

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
