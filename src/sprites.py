# Asteroid Impact (c) Media Neuroscience Lab, Rene Weber
# Authored by Nick Winters
# 
# Asteroid Impact is licensed under a
# Creative Commons Attribution-ShareAlike 4.0 International License.
# 
# You should have received a copy of the license along with this
# work. If not, see <http://creativecommons.org/licenses/by-sa/4.0/>. 
"""
AsteroidImpact game sprites including sprite-specific behaviors.
"""

import pygame
from resources import load_image, load_sound, NoneSound
import virtualdisplay
import math

CODE_BY_PYGAME_CONSTANT = {k: getattr(pygame, k) for k in dir(pygame) if k.startswith('K_')}
PYGAME_CONSTANT_BY_CODE = {getattr(pygame, k): k for k in dir(pygame) if k.startswith('K_')}


class QuitGame(Exception):
    """Exception to raise in update_xxx() to quit the game"""

    def __init__(self, value):
        """Create new QuitGame exception"""
        Exception.__init__(self)
        self.value = value

    def __str__(self):
        return repr(self.value)


class VirtualGameSprite(pygame.sprite.DirtySprite):
    """
    Sprite with higher resolution game position/size (gamerect) than on-screen
    position/size (rect)
    """

    def __init__(self):
        pygame.sprite.DirtySprite.__init__(self)  # call Sprite initializer
        self.dirty = 2  # always redraw
        self.gamerect = pygame.Rect(0, 0, 1, 1)

    def stop_audio(self):
        # override in derived classes
        pass

    def update_rect(self):
        self.rect = virtualdisplay.screenrect_from_gamerect(self.gamerect)


# classes for our game objects
class Cursor(VirtualGameSprite):
    """The Player's ship is moved around using the mouse cursor"""

    def __init__(self, game_bounds=virtualdisplay.GAME_PLAY_AREA):
        VirtualGameSprite.__init__(self)  # call Sprite initializer
        # find screen diameter
        self.gamediameter = 32
        self.gamerect = pygame.Rect(0, 0, self.gamediameter, self.gamediameter)
        self.game_bounds = game_bounds
        self.update_rect()
        self.image = load_image(
            'cursor.png',
            (self.rect.width, self.rect.height),
            convert_alpha=True)

    def update(self, millis):
        """Move the cursor based on the mouse position"""
        pos = pygame.mouse.get_pos()
        game_pos = virtualdisplay.gamepoint_from_screenpoint(pos)

        # if the cursor is outside of the game area, move it back
        if not self.game_bounds.collidepoint(game_pos):
            game_pos = (
                max(
                    min(game_pos[0], self.game_bounds.right),
                    self.game_bounds.left),
                max(
                    min(game_pos[1], self.game_bounds.bottom),
                    self.game_bounds.top))
            pos = virtualdisplay.screenpoint_from_gamepoint(game_pos)
            pygame.mouse.set_pos(pos)

        self.gamerect.center = game_pos
        self.update_rect()


class Target(VirtualGameSprite):
    """Targets (Crystals) don't move, but do play a sound when collected"""

    def __init__(self, diameter=32, left=20, top=20):
        VirtualGameSprite.__init__(self)  # call Sprite initializer
        self.gamediameter = diameter
        self.gamerect = pygame.Rect(left, top, diameter, diameter)
        self.update_rect()
        self.image = load_image(
            'crystal.png',
            (self.rect.width, self.rect.height),
            convert_alpha=True)
        self.pickup_sound = load_sound('ring_inventory.wav')

    def stop_audio(self):
        self.pickup_sound.stop()

    def pickedup(self):
        """Play pick up sound"""
        self.pickup_sound.play()

    def update(self, millis):
        # hit test done in AsteroidImpactGameplayScreen
        pass


class ScoredTarget(VirtualGameSprite):
    """Targets (Crystals) don't move, but do play a sound when collected"""

    def __init__(self,
                 diameter=32,
                 left=20,
                 top=20,
                 imagefile='crystal.png',
                 number='x',
                 # None or milliseconds until crystal disappears on its own:
                 lifetime_millis_max=None,
                 play_buzzer_on_negative_score=True):
        # todo: options for start/fadeout/end times
        # todo: option for scoring-number
        VirtualGameSprite.__init__(self)  # call Sprite initializer
        self.gamediameter = diameter
        self.gamerect = pygame.Rect(left, top, diameter, diameter)
        self.update_rect()
        self.image = load_image(
            imagefile,
            (self.rect.width, self.rect.height),
            convert_alpha=True)
        self.number = number
        self.visible = 0
        self.active = False
        self.pickup_sound = load_sound('ring_inventory.wav')
        self.pickup_sound_negative = load_sound('prompt_error.wav')
        self.flashing = False
        self.flashing_counter = 0

        # max time this crystal remains active
        self.lifetime_millis_max = lifetime_millis_max
        # current elapsed millis this crystal has been active
        self.lifetime_millis_elapsed = 0

        self.play_buzzer_on_negative_score = play_buzzer_on_negative_score

    def activate(self, life_multiplier=1):
        self.active = True
        self.visible = 1
        self.lifetime_millis_elapsed = 0
        if life_multiplier > 1 and self.lifetime_millis_max != None:
            # make this one appearance last n times as long by offsetting start of life
            self.lifetime_millis_elapsed -= int((life_multiplier - 1) * self.lifetime_millis_max)
        self.flashing = False
        self.flashing_counter = 0

    def deactivate(self):
        self.active = False
        self.visible = 0

    def stop_audio(self):
        self.pickup_sound.stop()
        self.pickup_sound_negative.stop()

    def pickedup(self, score=1):
        """Play pick up sound"""
        if self.play_buzzer_on_negative_score and score < 0:
            self.pickup_sound_negative.play()
        else:
            self.pickup_sound.play()
        self.deactivate()

    def update(self, millis):
        # hit test done in AsteroidImpactGameplayScreen
        if self.active:
            self.lifetime_millis_elapsed += millis

            # start flashing before end of self.lifetime_millis_max
            if (not self.flashing
                    and self.lifetime_millis_max != None
                    and self.lifetime_millis_max < self.lifetime_millis_elapsed + 2000):
                self.flashing = True

            if self.flashing:
                self.flashing_counter = (self.flashing_counter + 1) % 8
                self.visible = 1 if self.flashing_counter < 4 else 0
            elif self.active:
                self.flashing_counter = 0
                self.visible = 1

            if self.lifetime_millis_max != None and self.lifetime_millis_elapsed > self.lifetime_millis_max:
                # deactivate myself
                self.deactivate()


def map_range(value, from_low, from_high, to_low, to_high):
    'return value in range [from_low, from_high] mapped to range [to_low, to_high]'
    return to_low + (to_high - to_low) * (value - from_low) / (from_high - from_low)


def clamp_range(value, limit_low, limit_high):
    'return limit_low if value < limit_low, limit_high if value > limit_high, otherwise value'
    if (value < limit_low): return limit_low
    if (limit_high < value): return limit_high
    return value


class Asteroid(VirtualGameSprite):
    """Asteroids move in straight lines, bouncing off the edges of the game play area"""

    def __init__(self, diameter=200, dx=4, dy=10, left=20, top=20, area=None):
        VirtualGameSprite.__init__(self)  # call Sprite intializer
        self.gamediameter = diameter
        self.gamerect = pygame.Rect(left, top, diameter, diameter)
        self.update_rect()
        self.image = load_image(
            'asteroid.png',
            (self.rect.width, self.rect.height),
            convert_alpha=True)

        if area:
            self.GAME_PLAY_AREA = area
        else:
            self.GAME_PLAY_AREA = virtualdisplay.GAME_PLAY_AREA
        # rect uses integer positions but I need to handle fractional pixel/frame speeds.
        # store float x/y positions here:
        self.gametopfloat = float(top)
        self.gameleftfloat = float(left)
        self.dx = dx
        self.dy = dy
        self.speedfactor = 1.0
        self.gamediameternew_start_diameter = diameter
        self.gamediameternew_end_diameter = diameter
        self.gamediameternew_transition_duration_millis = 0
        self.gamediameternew_transition_remaining_millis = 0
        self.dxnew = self.dx
        self.dynew = self.dy

    def copy_from(self, asteroid):
        self.gamediameter = asteroid.gamediameter
        self.gamerect = asteroid.gamerect.copy()
        self.update_rect()
        self.image = load_image(
            'asteroid.png',
            (self.rect.width, self.rect.height),
            convert_alpha=True)
        self.GAME_PLAY_AREA = asteroid.GAME_PLAY_AREA
        self.gametopfloat = asteroid.gametopfloat
        self.gameleftfloat = asteroid.gameleftfloat
        self.dx = asteroid.dx
        self.dy = asteroid.dy
        self.gamediameternew_start_diameter = asteroid.gamediameter
        self.gamediameternew_end_diameter = asteroid.gamediameter
        self.gamediameternew_transition_duration_millis = 0
        self.gamediameternew_transition_remaining_millis = 0
        self.dxnew = self.dx
        self.dynew = self.dy

    def update(self, millis):
        """Update the position and direction of the Asteroid to move, and bounce"""

        # handle size transition:
        if (self.gamediameternew_transition_remaining_millis > 0):
            self.gamediameternew_transition_remaining_millis -= millis
            if (self.gamediameternew_transition_remaining_millis < 0):
                self.gamediameternew_transition_remaining_millis = 0

            # Transition diameter
            newdiameter = int(round(
                map_range(self.gamediameternew_transition_remaining_millis,
                          self.gamediameternew_transition_duration_millis,
                          0,
                          self.gamediameternew_start_diameter,
                          self.gamediameternew_end_diameter)))

            center = self.gamerect.center
            if (newdiameter != self.gamediameter):
                self.gamediameter = newdiameter
                self.gamerect.size = (newdiameter, newdiameter)
                self.gamerect.center = center
                self.update_rect()
                # resample image
                # TODO: is this too slow?
                # Yep, until the images are cached this is super slow
                self.image = load_image(
                    'asteroid.png',
                    (self.rect.width, self.rect.height),
                    convert_alpha=True)

        # when bouncing, change from expected X or Y speed towards
        # new speed by at most +/-4px/frame
        adjusted_abs_dx = clamp_range(abs(self.dxnew), max(abs(self.dx) - 4, 1), abs(self.dx) + 4)
        adjusted_abs_dy = clamp_range(abs(self.dynew), max(abs(self.dy) - 4, 1), abs(self.dy) + 4)

        # bounce by setting sign of x or y speed if off of corresponding side of screen
        if self.gamerect.left < self.GAME_PLAY_AREA.left:
            self.dx = adjusted_abs_dx
        if self.gamerect.right > self.GAME_PLAY_AREA.right:
            self.dx = -adjusted_abs_dx
        if self.gamerect.top < self.GAME_PLAY_AREA.top:
            self.dy = adjusted_abs_dy
        if self.gamerect.bottom > self.GAME_PLAY_AREA.bottom:
            self.dy = -adjusted_abs_dy

        self.gameleftfloat += self.dx * self.speedfactor
        self.gametopfloat += self.dy * self.speedfactor
        self.gamerect.left = self.gameleftfloat
        self.gamerect.top = self.gametopfloat
        self.update_rect()


class BasePowerup(VirtualGameSprite):
    """Base class for power-ups so they share common expiration behavior"""

    def __init__(self, diameter=16, left=50, top=50, maxduration=5.0):
        VirtualGameSprite.__init__(self)  # call Sprite initializer
        self.gamediameter = diameter
        # likely overwritten in derived class:
        self.gamerect = pygame.Rect(left, top, diameter, diameter)
        self.update_rect()

        self.maxduration = maxduration  # seconds
        self.active = False
        self.duration = 0

        self.used = False

    def update(self, millis, frame_outbound_triggers, cursor, asteroids):
        """Deactivate power-up if duration has expired"""
        if self.active:
            self.duration += millis / 1000.

            if self.duration > self.maxduration:
                # deactivate:
                self.deactivate(cursor, asteroids, frame_outbound_triggers)

    def activate(self, cursor, asteroids, frame_outbound_triggers, *args):
        """Activate power-up because it was picked up"""
        self.oldgamerect = self.gamerect.copy()
        self.active = True
        self.duration = 0
        self.used = False

    def deactivate(self, cursor, asteroids, frame_outbound_triggers):
        """Deactivate power-up"""
        self.active = False
        self.gamerect = self.oldgamerect
        self.update_rect()
        self.used = True
        self.kill()


class SlowPowerup(BasePowerup):
    """While active, the SlowPowerup slows the asteroids to a crawl"""

    def __init__(self, diameter=32, left=100, top=100):
        BasePowerup.__init__(self, diameter=diameter, left=left, top=top, maxduration=5.0)
        self.type = 'slow'
        self.gamerect = pygame.Rect(left, top, diameter, diameter)
        self.update_rect()
        self.image = load_image(
            'clock.png',
            (self.rect.width, self.rect.height),
            convert_alpha=True)

        self.sound_begin = load_sound('slow start.wav')
        self.sound_end = load_sound('slow end.wav')
        # these let me start the ending sound to end overlapping when the effect ends:
        self.sound_end_duration = self.sound_end.get_length() - 0.5
        self.sound_end_started = False

        self.speedfactor = 0.25

    def stop_audio(self):
        self.sound_end.stop()
        self.sound_begin.stop()

    def update(self, millis, frame_outbound_triggers, cursor, asteroids):
        """ Play effect end sound if due"""
        BasePowerup.update(self, millis, frame_outbound_triggers, cursor, asteroids)

        if self.active:
            # start the end effect sound to end when powerup ends:
            if (self.maxduration - self.duration < self.sound_end_duration
                    and not self.sound_end_started):
                self.sound_end_started = True
                self.sound_end.play()
            for asteroid in asteroids:
                asteroid.speedfactor = self.speedfactor

    def activate(self, cursor, asteroids, frame_outbound_triggers, *args):
        """Play start sound. Slow asteroids to a crawl"""
        BasePowerup.activate(self, cursor, asteroids, frame_outbound_triggers, *args)

        # adjust speed of asteroids
        for asteroid in asteroids:
            asteroid.speedfactor = self.speedfactor

        # disappear offscreen
        self.gamerect.top = -10000
        self.gamerect.left = -10000
        self.update_rect()

        self.sound_begin.play()

        self.sound_end_started = False

        frame_outbound_triggers.append('game_slow_activate')

    def deactivate(self, cursor, asteroids, frame_outbound_triggers, *args):
        """Restore normal speed of asteroids"""
        BasePowerup.deactivate(self, cursor, asteroids, frame_outbound_triggers, *args)

        # restore speed of asteroids
        for asteroid in asteroids:
            asteroid.speedfactor = 1.0


class ShieldPowerup(BasePowerup):
    """
    While active, the ShieldPowerup prevents the player from dying due to
    collisions with asteroids.
    """

    def __init__(self, diameter=32, left=80, top=80):
        BasePowerup.__init__(self, diameter=diameter, left=left, top=top, maxduration=5.0)
        self.type = 'shield'
        self.gamerect = pygame.Rect(left, top, diameter, diameter)
        self.update_rect()
        self.image = load_image(
            'shield.png',
            (self.rect.width, self.rect.height),
            convert_alpha=True)
        self.image = pygame.transform.smoothscale(
            self.image, (self.rect.width, self.rect.height))

        self.sound_begin = load_sound('shield start.wav')
        self.sound_end = load_sound('shield end.wav')
        # these let me start the ending sound to end overlapping when the effect ends:
        self.sound_end_duration = self.sound_end.get_length() - 1.0
        self.sound_end_started = False

    def stop_audio(self):
        self.sound_begin.stop()
        self.sound_end.stop()

    def activate(self, cursor, asteroids, frame_outbound_triggers, *args):
        """Play activation sound"""
        BasePowerup.activate(self, cursor, asteroids, frame_outbound_triggers, *args)

        self.sound_begin.play()

        self.sound_end_started = False

        frame_outbound_triggers.append('game_shield_activate')

    def update(self, millis, frame_outbound_triggers, cursor, asteroids):
        """Follow cursor. Play effect end sound if due"""
        BasePowerup.update(self, millis, frame_outbound_triggers, cursor, asteroids)
        if self.active:
            # follow on top of cursor:
            self.gamerect.center = cursor.gamerect.center
            self.update_rect()

            # "ignore collisions" logic happens in Game Screen

            # start the end effect sound to end when powerup ends:
            if (self.maxduration - self.duration < self.sound_end_duration
                    and not self.sound_end_started):
                self.sound_end_started = True
                self.sound_end.play()


class NonePowerup(BasePowerup):
    """This power-up has no effect except delaying the next power-up from spawning"""

    def __init__(self, duration=10.0):
        # configure as a circle completely covering the screen so I get picked up
        # as soon as available
        diameter = 10 * virtualdisplay.GAME_PLAY_AREA.width
        self.gamerect = pygame.Rect(0, 0, diameter, diameter)
        self.gamerect.centerx = virtualdisplay.GAME_PLAY_AREA.width // 2
        self.gamerect.centery = virtualdisplay.GAME_PLAY_AREA.height // 2
        BasePowerup.__init__(
            self,
            diameter=diameter,
            left=self.gamerect.left,
            top=self.gamerect.top,
            maxduration=duration)
        self.type = 'none'
        self.image = None
        self.update_rect()


class ReactionTimePrompt(VirtualGameSprite):
    """Game element to test reaction time"""

    def __init__(
            self,
            diameter=64,
            position_list=[[20, 20]],
            sound='tone440.wav',
            image='triangle.png',
            input_key='K_1',
            showtimes_millis=[],
            showtimes_trigger_counts=[],
            timeout_millis=5000,
            stay_visible=False,
            score_pass=None,
            score_fail=None,
            score_miss=None,
            fail_on_wrong_key=False,
            pass_fail_sounds=False,
            **kwargs_extra):
        # if kwargs_extra: print 'extra arguments:', kwargs_extra
        VirtualGameSprite.__init__(self)  # call Sprite initializer
        self.gamediameter = diameter
        self.position_list = position_list
        self.position_index = -1
        left, top = self.position_list[self.position_index]
        self.gamerect_visible = pygame.Rect(left, top, diameter, diameter)
        self.gamerect_hidden = pygame.Rect(-9999, -9999, diameter, diameter)
        self.gamerect = self.gamerect_hidden
        self.update_rect()

        if not image or image == 'none':
            image = 'transparent.png'
        self.image = load_image(
            image,
            (self.rect.width, self.rect.height),
            convert_alpha=True)
        self.image_name = image

        if sound and sound != 'none':
            self.prompt_sound = load_sound(sound, mixing_group='reaction')
            self.sound_name = sound
        else:
            self.prompt_sound = NoneSound()
            self.sound_name = 'none'

        if pass_fail_sounds:
            self.pass_sound = load_sound('prompt_correct.wav', mixing_group='reaction')
            self.fail_sound = load_sound('prompt_error.wav', mixing_group='reaction')
        else:
            self.pass_sound = NoneSound()
            self.fail_sound = NoneSound()

        self.showtimes_millis = showtimes_millis
        # todo: implement trigger showing
        self.showtimes_trigger_counts = showtimes_trigger_counts
        if isinstance(timeout_millis, str) or isinstance(timeout_millis, str):
            timeout_millis = None
        self.timeout_millis = timeout_millis
        self.stay_visible = stay_visible
        self.score_pass = score_pass
        self.score_fail = score_fail
        self.score_miss = score_miss
        self.fail_on_wrong_key = fail_on_wrong_key
        self.active = False
        self.visible = False
        self.total_elapsed = 0
        self.showtime_last = 0  # millis when shown
        self.step_trigger_count_last = 0
        if input_key.startswith('K_MOUSE'):
            mousebutton_index = 0
            if input_key == 'K_MOUSE1':
                mousebutton_index = 0  # left mouse
            elif input_key == 'K_MOUSE2':
                mousebutton_index = 1  # middle mouse
            elif input_key == 'K_MOUSE3':
                mousebutton_index = 2  # right mouse
            else:
                raise QuitGame('mouse button for input_key for reaction prompt of %s is not recognized' % input_key)
                raise QuitGame()

            self.dismiss_test = lambda evt: evt.type == pygame.MOUSEBUTTONDOWN and pygame.mouse.get_pressed()[
                mousebutton_index]
        else:
            # input_key should correspond to actual key
            pygame_key_constant = getattr(pygame, input_key, None)
            if not pygame_key_constant:
                print('input_key of "%s" not found. Please use one of the following' % input_key)
                print(', '.join(['"' + s + '"' for s in list(CODE_BY_PYGAME_CONSTANT.keys())] + ['K_MOUSE1', 'K_MOUSE2',
                                                                                                 'K_MOUSE3']))
                raise QuitGame('input_key of "%s" not found. ' % input_key)
            self.dismiss_test = lambda evt: evt.type == pygame.KEYDOWN and evt.key == pygame_key_constant

    def isactive_and_dismiss_test(self, event):
        '''
        Returns True when prompt is active and the event matches the configured key/mouse button
        '''
        return (self.visible and
                self.active and
                self.dismiss_test(event))

    def activate_and_show(self):
        # prepare for next position:
        self.position_index = (self.position_index + 1) % len(self.position_list)
        left, top = self.position_list[self.position_index]
        self.gamerect_visible = pygame.Rect(left, top, self.gamediameter, self.gamediameter)

        self.gamerect = self.gamerect_visible
        self.update_rect()
        self.active = True
        self.visible = True
        self.prompt_sound.play()

    def deactivate_and_hide(self):
        self.gamerect = self.gamerect_hidden
        self.update_rect()
        self.active = False
        self.visible = False

        # fadeout avoids "click" at end, but I wish I could do shorter duration
        self.prompt_sound.fadeout(100)

    def key_from_event(self, event):
        # todo
        if event.type == pygame.MOUSEBUTTONDOWN:
            return 'K_MOUSE%d' % (event.button)
        elif event.type == pygame.KEYDOWN:
            # todo: convert this back into a constant
            if event.key in PYGAME_CONSTANT_BY_CODE:
                return PYGAME_CONSTANT_BY_CODE[event.key]
            return "Unknown"
        else:
            # todo: what can I do here?
            return "Unknown"

    def update(self, millis, logrowdetails, reactionlogger, frame_outbound_triggers, events, step_trigger_count):
        endingtype = None  # or 'pass' or 'fail', returned at the end
        old_total_elapsed = self.total_elapsed
        self.total_elapsed += millis

        if not self.visible:
            for showtime in self.showtimes_millis:
                if (old_total_elapsed < showtime and
                        showtime <= self.total_elapsed):
                    # show
                    self.showtime_last = self.total_elapsed
                    self.activate_and_show()
            if (not self.visible
                    and self.step_trigger_count_last != step_trigger_count
                    and self.showtimes_trigger_counts
                    and step_trigger_count in self.showtimes_trigger_counts):
                # show
                self.showtime_last = self.total_elapsed
                self.activate_and_show()
        else:
            visible_ms = self.total_elapsed - self.showtime_last
            logrowdetails['reaction_prompt_state'] = 'waiting'
            logrowdetails['reaction_prompt_millis'] = visible_ms
            logrowdetails['reaction_prompt_sound'] = self.sound_name
            logrowdetails['reaction_prompt_image'] = self.image_name

            if self.active:
                # showing now and waiting keypress
                for event in events:
                    if self.dismiss_test(event):
                        # correct key pressed
                        logrowdetails['reaction_prompt_state'] = 'complete'
                        logrowdetails['reaction_prompt_millis'] = visible_ms
                        logrowdetails['reaction_prompt_passed'] = 'true'
                        logrowdetails['reaction_prompt_pressed_key'] = self.key_from_event(event)

                        if self.stay_visible:
                            # just deactivate, don't hide or stop playing sounds until timeout
                            self.active = False
                        else:
                            self.deactivate_and_hide()

                        self.pass_sound.play()

                        # log completed
                        self.logme(logrowdetails, reactionlogger)
                        endingtype = 'pass'
                        break
                    elif self.fail_on_wrong_key:
                        # failed on incorrect key presss
                        logrowdetails['reaction_prompt_state'] = 'failed'
                        logrowdetails['reaction_prompt_millis'] = visible_ms
                        logrowdetails['reaction_prompt_passed'] = 'false'
                        logrowdetails['reaction_prompt_pressed_key'] = self.key_from_event(event)

                        if self.stay_visible:
                            # just deactivate, don't hide or stop playing sounds until timeout
                            self.active = False
                        else:
                            self.deactivate_and_hide()

                        self.fail_sound.play()

                        # log completed
                        self.logme(logrowdetails, reactionlogger)
                        endingtype = 'fail'
                        break
            else:
                # no longer active because key was already pressed.
                logrowdetails['reaction_prompt_state'] = 'after_complete'

            if self.timeout_millis:
                if self.showtime_last + self.timeout_millis <= self.total_elapsed:
                    # stayed visible entire time allowed
                    # might be because was supposed to stay visible after key press, so check before logging/notifying
                    if self.active:
                        # still waiting for key that didn't happen in time, log it
                        logrowdetails['reaction_prompt_state'] = 'timeout'
                        logrowdetails['reaction_prompt_millis'] = visible_ms
                        logrowdetails['reaction_prompt_passed'] = 'false'

                        self.fail_sound.play()

                        # log timed out
                        self.logme(logrowdetails, reactionlogger)
                        endingtype = 'timeout'

                    self.deactivate_and_hide()

        self.step_trigger_count_last = step_trigger_count
        return endingtype

    def step_end_deactivate(self, logrowdetails, reactionlogger):
        if self.visible:
            self.prompt_sound.stop()
            # log timeout_step_end
            visible_ms = self.total_elapsed - self.showtime_last
            logrowdetails['reaction_prompt_sound'] = self.sound_name
            logrowdetails['reaction_prompt_image'] = self.image_name
            logrowdetails['reaction_prompt_state'] = 'timeout_step_end'
            logrowdetails['reaction_prompt_millis'] = visible_ms
            self.logme(logrowdetails, reactionlogger)

    def logme(self, logrowdetails, reactionlogger):
        newreactionlogrow = {}
        for col in reactionlogger.columns:
            if col in logrowdetails:
                newreactionlogrow[col] = logrowdetails[col]
        reactionlogger.log(newreactionlogrow)


class ReactionTimePromptGroup(pygame.sprite.OrderedUpdates):
    def __init__(self, prompt_settings_list):
        if prompt_settings_list == None:
            prompt_settings_list = []
        pygame.sprite.OrderedUpdates.__init__(self)

        # todo: add a score change sprite?

        for rp in prompt_settings_list:
            new_reaction_prompt = ReactionTimePrompt(**rp)
            self.add(new_reaction_prompt)

    # draw() implemented in superclass

    def update(self, millis, logrowdetails, reactionlogger, frame_outbound_triggers, events, step_trigger_count):
        '''
        update all contained reaction prompts.

        returns list of score change dictionary entries:
            [{change=123,centerx=456.0,centery=789.0},{change=-10,centerx=123.0,centery=123.0}]

        The events sent to each prompt are pre-processed to either include
        events that trigger that prompt, or ones that didn't match another
        prompt. This is so that when multiple prompts are active, and pressing
        the wrong key is configured to fail them both, pressing the key for
        just one of the prompts does not fail the other.
        '''
        score_changes = []

        # filter events to only key down or mouse button down
        events_filtered = []
        for evt in events:
            if (evt.type == pygame.MOUSEBUTTONDOWN or evt.type == pygame.KEYDOWN):
                events_filtered.append(evt)

        # pass 1: filter event list for each prompt
        events_by_prompt_index = [None] * len(self)
        events_matched_all = []  # all events that matched one or more active prompt
        for i, prompt in enumerate(self):
            matching_event_list = [evt for evt in events if prompt.isactive_and_dismiss_test(evt)]
            if len(matching_event_list) == 0:
                # use unprocessed events
                # is filled below
                events_by_prompt_index[i] = None
            else:
                # use only matching events
                events_by_prompt_index[i] = matching_event_list
                events_matched_all.extend(matching_event_list)

        events_unmatched = [evt for evt in events_filtered if evt not in events_matched_all]
        # replace None entries with events_unmatched in events_by_prompt_index
        events_by_prompt_index = [evt or events_unmatched for evt in events_by_prompt_index]

        # pass 2: respond to correct or incorrect keypresses
        for i, prompt in enumerate(self):
            prompt_events = events_by_prompt_index[i]
            prompt_gamerect_before = prompt.gamerect
            endingtype = prompt.update(
                millis,
                logrowdetails,
                reactionlogger,
                frame_outbound_triggers,
                prompt_events,
                step_trigger_count)
            if endingtype == 'pass' and prompt.score_pass != None:
                score_changes.append(dict(
                    change=prompt.score_pass,
                    centerx=prompt_gamerect_before.centerx,
                    centery=prompt_gamerect_before.centery))

            elif endingtype == 'fail' and prompt.score_fail != None:
                score_changes.append(dict(
                    change=prompt.score_fail,
                    centerx=prompt_gamerect_before.centerx,
                    centery=prompt_gamerect_before.centery))

            elif endingtype == 'timeout' and prompt.score_fail != None:
                score_changes.append(dict(
                    change=prompt.score_miss,
                    centerx=prompt_gamerect_before.centerx,
                    centery=prompt_gamerect_before.centery))

        return score_changes


class TextSprite(object):
    """
    Sprite-like object for text that helps positioning text in game coordinates, and
    keeping text in position when text changes.
    """

    def __init__(self, font, text, color, **kwargs):
        """
        Create new TextSprite()

        Keyword arguments are transformed from game space to screen space and used to specify
        position of rasterized text.
        """
        self.font = font
        self.color = color
        self.text = None
        self.textsurf = None
        self.set_position(**kwargs)
        self.set_text(text)

    def set_position(self, **kwargs):
        for arg in list(kwargs.keys()):
            # convert some args from game coordinate space to screen coordinate space
            if arg == 'x' or arg == 'left' or arg == 'right' or arg == 'centerx':
                kwargs[arg] = virtualdisplay.screenpoint_from_gamepoint((kwargs[arg], 0))[0]
            elif arg == 'y' or arg == 'top' or arg == 'bottom' or arg == 'centery':
                kwargs[arg] = virtualdisplay.screenpoint_from_gamepoint((0, kwargs[arg]))[1]
            else:
                raise ValueError(
                    "TextSprite() doesn't implement support for rect keword arg '%s'" % arg)
        self.textsurf_get_rect_args = kwargs
        if self.textsurf:
            self.textrect = self.textsurf.get_rect(**self.textsurf_get_rect_args)

    def set_text(self, text):
        """Set and render new text"""
        if text != self.text:
            self.text = text
            self.textsurf = self.font.render(self.text, 1, self.color)
        self.textrect = self.textsurf.get_rect(**self.textsurf_get_rect_args)

    def draw(self, screen):
        """Draw text on screen"""
        screen.blit(self.textsurf, self.textrect)


class Overlay(VirtualGameSprite):
    def __init__(
            self,
            lifetime_millis_elapsed=0,
            w=virtualdisplay.screenplayarea.width,
            h=virtualdisplay.screenplayarea.height,
            visible=0,
            **kwargs_extra):
        # if kwargs_extra: print 'extra arguments:', kwargs_extra
        VirtualGameSprite.__init__(self)  # call Sprite initializer
        self.gamediameter = w
        left, top = [0, 0]
        self.gamerect_visible = pygame.Rect(left, top, w, h)
        self.gamerect_hidden = pygame.Rect(-9999, -9999, w, h)
        self.gamerect = self.gamerect_hidden
        self.update_rect()
        if not image or image == 'none':
            image = 'transparent.png'
        self.image = load_image(image,
                                (virtualdisplay.screenplayarea.width,
                                 virtualdisplay.screenplayarea.height),
                                convert_alpha=False)
        self.elapsed = lifetime_millis_elapsed
        self.flashing_counter = 0
        self.visible = visible
        self.counter = 0

    def draw(self, screen):
        """Draw text on screen"""
        screen.blit(self.image, virtualdisplay.screenarea.topleft)

    def update(self, millis):
        # hit test done in AsteroidImpactGameplayScreen
        self.counter += millis
        self.flashing_counter = (self.flashing_counter + 1) % 80
        self.visible = 0 if self.flashing_counter <= 4 else 1
