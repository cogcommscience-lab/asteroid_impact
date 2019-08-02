# Asteroid Impact (c) Media Neuroscience Lab, Rene Weber
# Authored by Nick Winters
#
# Asteroid Impact is licensed under a
# Creative Commons Attribution-ShareAlike 4.0 International License.
#
# You should have received a copy of the license along with this
# work. If not, see <http://creativecommons.org/licenses/by-sa/4.0/>.
"""
Game screens for AsteroidImpact
"""

import random
import string

from pygame.locals import *

import parallelportwrapper
import virtualdisplay
from makelevel import make_level, TARGET_SIZE
from resources import load_font, load_image, mute_music, unmute_music
from sprites import *


# screens.py
class GameScreen(object):
    """Base class for AsteroidImpact game screens"""

    def __init__(self, screen, screenstack):
        """Initialize the base members of GameScreen"""
        self.screen = screen
        self.screenstack = screenstack
        self.opaque = True
        self.name = self.__class__.__name__

    def update_frontmost(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count,
                         reactionlogger):
        """Update the screen's game state when this screen is frontmost"""
        pass

    def update_always(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count, reactionlogger):
        """Update the screen's game state every iteration regardless of if another screen is stacked on top"""
        pass

    def draw(self):
        """Draw the game screen to the physical screen buffer"""
        pass

    def after_close(self, logrowdetails, reactionlogger, surveylogger):
        """Clean up after screen is closed, and perform additional logging"""
        pass


class BlackScreen(GameScreen):
    """
    Black screen. Shown to the player while other things are happening in other parts of
    the research. The player can't interact with the black screen.
    """

    def __init__(self, screen, gamescreenstack):
        GameScreen.__init__(self, screen, gamescreenstack)
        self.name = 'black'
        self.opaque = True
        self.screenarea = self.screen.get_rect()

        self.background = pygame.Surface(screen.get_size())
        self.background = self.background.convert()
        self.background.fill((0, 0, 0))

        self.first_update = True

    def update_frontmost(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count,
                         reactionlogger):
        if self.first_update:
            self.first_update = False
            # don't play music during the black screen
            mute_music()

    def draw(self):
        # draw background
        self.screen.blit(self.background, (0, 0))


def font_find_fitting_string_length(font, line, line_width_screenpx):
    """return the length (in characters) of the string that fits within lineWidth"""
    for i in range(len(line), -1, -1):
        if font.size(line[0:i])[0] <= line_width_screenpx:
            return i
    return len(line)


def valid_breakpoint_character(c):
    """return true when c is a valid word-wrapping breakpoint character"""
    # whitespace:
    return c in string.whitespace


def flow_text(text, bounds_rect, font, color, line_height, valign='middle'):
    """Flow text into rectangle. Returns list of text elements and rectangle bounds of result."""
    lines = text.split('\n')

    bounds_rect_screen = virtualdisplay.screenrect_from_gamerect(bounds_rect)

    wrapped_lines = []
    for line in lines:
        line = line.strip()
        wrappedline = True
        while wrappedline:
            wrappedline = False

            maxlength = font_find_fitting_string_length(
                font, line, bounds_rect_screen.width)
            if maxlength < len(line):
                wrappedline = True
                # find text breakpoint
                breakpointlength = maxlength
                while (breakpointlength > 0 and
                       not valid_breakpoint_character(line[breakpointlength - 1])):
                    breakpointlength -= 1
                if breakpointlength == 0:
                    # likely a long single word or URL. Just break where it fits
                    breakpointlength = maxlength
                lineremainder = line[breakpointlength:]
                line = line[:breakpointlength]

            wrapped_lines.append(line)

            if wrappedline:
                # trim starting whitespace if any after line break
                line = lineremainder.lstrip()

    # add text blocks, but vertically center them all on screen
    y = bounds_rect.top
    if valign == 'middle': y = bounds_rect.top + (bounds_rect.height - (len(wrapped_lines) * line_height)) / 2
    if valign == 'bottom': y = bounds_rect.bottom - (len(wrapped_lines) * line_height)
    top = y
    sprites = []
    for line in wrapped_lines:
        sprites.append(TextSprite(
            font,
            line,
            color,
            x=bounds_rect.left + 50,
            y=y))
        y += line_height
    return sprites, Rect(bounds_rect.left, top, bounds_rect.width, y - top)


class UserTextScreen(GameScreen):
    """
    Text Screen. Displays text specified in step.
    """

    def __init__(self, screen, gamescreenstack, click_to_continue=True, text="[No text value was specified]", title=""):
        GameScreen.__init__(self, screen, gamescreenstack)
        self.click_to_continue = click_to_continue
        self.name = 'textdisplay'
        self.opaque = True
        self.blackbackground = pygame.Surface(self.screen.get_size())
        self.blackbackground = self.blackbackground.convert()
        self.blackbackground.fill((0, 0, 0))

        self.textsprites = []
        self.sprites = pygame.sprite.Group()

        big_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 72, 72)).height
        self.font_big = load_font('Ubuntu-M.ttf', big_font_size)
        self.line_height_big = 81

        self.line_height = 36  # game-space like font size below
        small_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 32, 32)).height
        self.font = load_font('Ubuntu-M.ttf', small_font_size)

        self.text_color = (250, 250, 250)  # white

        self.init_text(text, title)

        if self.click_to_continue:
            self.textsprites.append(TextSprite(
                self.font_big, "Click To Begin", self.text_color,
                centerx=virtualdisplay.GAME_AREA.width / 2,
                bottom=virtualdisplay.GAME_AREA.height))

        self.first_update = True

    def init_text(self, text, title):
        remaining_bounds = virtualdisplay.GAME_AREA
        if title:
            title_lines, title_result_bounds = flow_text(
                title,
                remaining_bounds,
                self.font_big,
                self.text_color,
                self.line_height_big,
                valign='top')
            self.textsprites += title_lines

            # reduce remaining_bounds to start at bottom of title_result_bounds
            remaining_bounds.height -= title_result_bounds.height
            remaining_bounds.y = title_result_bounds.bottom

        lines, result_bounds = flow_text(
            text,
            virtualdisplay.GAME_AREA,
            self.font,
            self.text_color,
            self.line_height,
            valign='middle')

        self.textsprites += lines

    def draw(self):
        # draw background
        self.screen.blit(self.blackbackground, (0, 0))
        # draw all text blocks:
        for textsprite in self.textsprites:
            textsprite.draw(self.screen)

    def update_frontmost(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count,
                         reactionlogger):
        if self.first_update:
            self.first_update = False
            # don't play music:
            mute_music()

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                if self.click_to_continue:
                    # position cursor at the center
                    pygame.mouse.set_pos([
                        virtualdisplay.screenarea.centerx,
                        virtualdisplay.screenarea.centery])
                    # end the instructions screen:
                    self.screenstack.pop()
                    # game.py will switch to gameplay
            elif event.type is MOUSEBUTTONUP:
                pass


class SurveyButton:
    '''Push button for "next" or toggle/radio button'''

    def __init__(self, gamerect, text, onclick, option_index=-1):
        self.gamerect = gamerect
        self.screenrect = virtualdisplay.screenrect_from_gamerect(gamerect)

        self.text = text
        self.option_index = option_index

        self.color_normal = (68, 68, 68)  # gray
        self.color_selected = (23, 100, 214)  # blue
        self.color_highlight = (222, 199, 67)  # yellow
        self.color_pressing = (231, 233, 35)  # yellow/orange

        self.buttonbackground = pygame.Surface((self.screenrect.width, self.screenrect.height))
        self.buttonbackground = self.buttonbackground.convert()
        self.buttonbackground.fill(self.color_normal)

        self.cursor_over = False
        self.selected = False
        self.mouse_button_was_down = False
        self.mouse_button_pressed_inside = False
        self.onclick = onclick

    def update(self, milliseconds):
        pos = pygame.mouse.get_pos()
        overlapping_me = False
        self.screenrect.collidepoint(pos)

        mouse_button_down = pygame.mouse.get_pressed()[0]

        '''
        states:
         * normal
         * selected
         * highlight (mouse over)
         * pressing (mouse over while pressed down on this object)

        normal/selected happen when:
         * mouse is up
         * mouse is down but wasn't pressed on this object but is overlapping it
        '''
        if mouse_button_down:
            if not self.mouse_button_was_down:
                # mouse left button now pressed
                self.mouse_button_pressed_inside = overlapping_me
            if overlapping_me:
                self.buttonbackground.fill(self.color_pressing)
            elif self.selected:
                self.buttonbackground.fill(self.color_selected)
            else:
                self.buttonbackground.fill(self.color_normal)
        if not mouse_button_down:
            if self.mouse_button_was_down:
                # mouse button released
                if self.mouse_button_pressed_inside and overlapping_me:
                    # self.selected = not self.selected
                    if self.onclick: self.onclick(self)

            if overlapping_me:
                self.buttonbackground.fill(self.color_highlight)
            elif self.selected:
                self.buttonbackground.fill(self.color_selected)
            else:
                self.buttonbackground.fill(self.color_normal)

        self.mouse_button_was_down = mouse_button_down

    def draw(self, screen):
        screen.blit(self.buttonbackground, (self.screenrect.left, self.screenrect.top))


class SurveyQuestionScreen(GameScreen):
    """
    Survey Question Screen. Prompt the player for the answer to a single multiple-choice question.
    """

    def __init__(
            self,
            screen,
            gamescreenstack,
            prompt="[No prompt value was specified]",
            survey_options=["[default choice]"],
            click_to_continue=True):
        GameScreen.__init__(self, screen, gamescreenstack)
        self.name = 'surveyquestion'
        self.prompt = prompt
        self.click_to_continue = click_to_continue
        # self.survey_options = survey_options
        self.opaque = True
        self.blackbackground = pygame.Surface(self.screen.get_size())
        self.blackbackground = self.blackbackground.convert()
        self.blackbackground.fill((0, 0, 0))

        self.sprites = pygame.sprite.OrderedUpdates()
        s = Cursor(game_bounds=virtualdisplay.GAME_AREA)
        s.gamerect.topleft = (120, 120)
        s.update_rect()
        self.sprites.add(s)

        self.textsprites = []

        big_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 72, 72)).height
        self.font_big = load_font('Ubuntu-M.ttf', big_font_size)

        self.line_height = 36  # game-space like font size below
        small_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 32, 32)).height
        self.font = load_font('Ubuntu-M.ttf', small_font_size)

        self.text_color = (250, 250, 250)  # white
        self.text_color_option = (250, 250, 250)  # white

        # init text for prompt
        lines, result_bounds = flow_text(
            prompt,
            virtualdisplay.GAME_AREA,
            self.font,
            self.text_color,
            self.line_height,
            valign='top')
        self.textsprites += lines

        # used for placement of answers
        bottom_y = virtualdisplay.GAME_AREA.bottom

        # add "next" button on bottom
        if self.click_to_continue:
            next_text = "Next..."
            lines, option_bounds = flow_text(
                next_text,
                virtualdisplay.GAME_AREA,
                self.font,
                self.text_color_option,
                self.line_height,
                valign='bottom')
            bottom_y -= (len(lines) + 1) * self.line_height
            self.textsprites += lines
            self.nextbutton = SurveyButton(option_bounds, next_text, lambda b: self.next_button_clicked())
        else:
            self.nextbutton = None

        # add buttons for each survey option
        self.option_buttons = []
        for option_index, option_text in reversed(list(enumerate(survey_options))):
            lines, option_bounds = flow_text(
                option_text,
                pygame.Rect(
                    virtualdisplay.GAME_AREA.left,
                    virtualdisplay.GAME_AREA.top,
                    virtualdisplay.GAME_AREA.width,
                    virtualdisplay.GAME_AREA.height - (virtualdisplay.GAME_AREA.bottom - bottom_y)),
                self.font,
                self.text_color_option,
                self.line_height,
                valign='bottom')
            bottom_y -= (len(lines) + 1) * self.line_height
            self.textsprites += lines
            option_button = SurveyButton(option_bounds, option_text, lambda b: self.option_button_click(b),
                                         option_index)
            self.option_buttons.append(option_button)

        self.first_update = True

    def draw(self):
        # draw background
        self.screen.blit(self.blackbackground, (0, 0))

        # draw buttons
        for b in self.option_buttons:
            b.draw(self.screen)
        if self.nextbutton:
            self.nextbutton.draw(self.screen)

        # draw all text blocks:
        for textsprite in self.textsprites:
            textsprite.draw(self.screen)

        self.sprites.draw(self.screen)

    def update_frontmost(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count,
                         reactionlogger):
        if self.first_update:
            self.first_update = False
            # don't play music:
            mute_music()

        self.sprites.update(millis)

        logrowdetails['survey_answer'] = 'MISSING'
        for b in self.option_buttons:
            b.update(millis)
            if b.selected:
                logrowdetails['survey_answer'] = b.text
                logrowdetails['survey_answer_number'] = b.option_index + 1
        logrowdetails['survey_prompt'] = self.prompt

        if self.nextbutton:
            self.nextbutton.update(millis)

    def option_button_click(self, button):
        # deselect all buttons
        for b in self.option_buttons:
            b.selected = False
        # select button that was clicked
        button.selected = True

    def next_button_clicked(self):
        # always close survey step:
        self.screenstack.pop()

    def after_close(self, logrowdetails, reactionlogger, surveylogger):
        """Clean up after screen is closed, and perform additional logging"""
        # save survey response in log. Already in logrowdetails
        # also save every other log column that's known
        surveylogrow = {}
        for col in surveylogger.columns:
            if col in logrowdetails:
                surveylogrow[col] = logrowdetails[col]
        surveylogger.log(surveylogrow)


class AsteroidImpactInstructionsScreen(GameScreen):
    """
    Instructions Screen. Displays the game objects (ship, crystal, etc) and rules to the player.
    """

    def __init__(self, screen, gamescreenstack, click_to_continue=True):
        GameScreen.__init__(self, screen, gamescreenstack)
        self.click_to_continue = click_to_continue
        self.name = 'instructions'
        self.opaque = True
        self.blackbackground = pygame.Surface(self.screen.get_size())
        self.blackbackground = self.blackbackground.convert()
        self.blackbackground.fill((0, 0, 0))

        self.gamebackground = load_image('background4x3_dark.jpg', size=virtualdisplay.screenarea.size)
        # draw gamebackground on blackbackground to only have to draw black/game once per frame:
        self.blackbackground.blit(self.gamebackground, virtualdisplay.screenarea.topleft)

        self.textsprites = []
        self.sprites = pygame.sprite.Group()

        big_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 72, 72)).height
        small_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 32, 32)).height
        self.font_big = load_font('Ubuntu-M.ttf', big_font_size)
        red = (250, 250, 10)
        black = (255, 255, 255)
        self.font = load_font('Ubuntu-M.ttf', small_font_size)
        self.textsprites.append(
            TextSprite(self.font_big, "How to Play", red,
                       centerx=virtualdisplay.GAME_AREA.width / 2,
                       top=0))

        s = Cursor()
        s.gamerect.topleft = (120, 120)
        s.update_rect()
        self.sprites.add(s)
        self.textsprites.append(
            TextSprite(
                self.font,
                "Move your ship around with your mouse, picking up crystals",
                black, left=240, top=120))

        s = Target()
        s.gamerect.topleft = (120, 240)
        s.update_rect()
        self.sprites.add(s)
        self.textsprites.append(TextSprite(
            self.font, "Pick up all the crystals", black,
            left=240, top=240))

        s = Asteroid(diameter=32)
        s.gamerect.topleft = (120, 360)
        s.update_rect()
        self.sprites.add(s)
        asteroidgamebounds = pygame.Rect(120, 400, 960 - 120 - 120, 160)
        self.asteroids = pygame.sprite.Group([
            Asteroid(diameter=64,
                     dx=1.5,
                     dy=1.0,
                     top=asteroidgamebounds.top,
                     left=asteroidgamebounds.left,
                     area=asteroidgamebounds),
            Asteroid(diameter=80,
                     dx=2.5,
                     dy=-1,
                     top=asteroidgamebounds.top + 20,
                     left=asteroidgamebounds.left + 400,
                     area=asteroidgamebounds),
            Asteroid(diameter=40,
                     dx=-1,
                     dy=-3,
                     top=asteroidgamebounds.top + 40,
                     left=asteroidgamebounds.left + 600,
                     area=asteroidgamebounds)])
        self.textsprites.append(
            TextSprite(
                self.font,
                "Avoid the bouncing asteroids. Hit one and it's game over.",
                black, left=240, top=360))

        s = ShieldPowerup()
        s.gamerect.topleft = (120, 600)
        s.update_rect()
        self.sprites.add(s)
        self.textsprites.append(TextSprite(
            self.font,
            "Pick up a shield to pass through asteroids for a few seconds",
            black, left=240, top=600))

        s = SlowPowerup()
        s.gamerect.topleft = (120, 720)
        s.update_rect()
        self.sprites.add(s)
        self.textsprites.append(TextSprite(
            self.font,
            "Pick up a clock to slow asteroids for a few seconds",
            black, left=240, top=720))

        if self.click_to_continue:
            self.textsprites.append(TextSprite(
                self.font_big, "Click To Begin", red,
                centerx=virtualdisplay.GAME_AREA.width / 2,
                bottom=virtualdisplay.GAME_AREA.height))

        self.first_update = True

    def draw(self):
        # draw background
        self.screen.blit(self.blackbackground, (0, 0))
        # draw all text blocks:
        for textsprite in self.textsprites:
            textsprite.draw(self.screen)
        self.sprites.draw(self.screen)
        self.asteroids.draw(self.screen)

    def update_frontmost(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count,
                         reactionlogger):
        if self.first_update:
            self.first_update = False
            # play music during the instructions at specified volume:
            unmute_music()

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                if self.click_to_continue:
                    # position cursor at the center
                    pygame.mouse.set_pos([
                        virtualdisplay.screenarea.centerx,
                        virtualdisplay.screenarea.centery])
                    # end the instructions screen:
                    self.screenstack.pop()
                    # game.py will switch to gameplay
            elif event.type is MOUSEBUTTONUP:
                pass

        # update asteroid positions
        for asteroid in self.asteroids:
            asteroid.update(millis)


class AsteroidImpactInstructionsScreenAlt(GameScreen):
    """
    Instructions Screen. Displays the game objects (ship, crystal, etc) and rules to the player.
    """

    def __init__(self, screen, gamescreenstack, click_to_continue=True):
        GameScreen.__init__(self, screen, gamescreenstack)
        self.click_to_continue = click_to_continue
        self.name = 'instructions_alt'
        self.opaque = True
        self.blackbackground = pygame.Surface(self.screen.get_size())
        self.blackbackground = self.blackbackground.convert()
        self.blackbackground.fill((0, 0, 0))

        self.gamebackground = load_image('background4x3_dark.jpg', size=virtualdisplay.screenarea.size)
        # draw gamebackground on blackbackground to only have to draw black/game once per frame:
        self.blackbackground.blit(self.gamebackground, virtualdisplay.screenarea.topleft)

        self.textsprites = []
        self.sprites = pygame.sprite.Group()

        big_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 72, 72)).height
        small_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 32, 32)).height
        self.font_big = load_font('Ubuntu-M.ttf', big_font_size)
        red = (250, 250, 10)
        black = (255, 255, 255)
        self.font = load_font('Ubuntu-M.ttf', small_font_size)
        self.textsprites.append(
            TextSprite(self.font_big, "How to Play", red,
                       centerx=virtualdisplay.GAME_AREA.width / 2,
                       top=10))

        s = Cursor()
        s.gamerect.topleft = (120, 120)
        s.update_rect()
        self.sprites.add(s)
        self.textsprites.append(
            TextSprite(
                self.font,
                "Move your ship around with your mouse, picking up crystals",
                black, left=240, top=120))

        s = Target()
        s.gamerect.topleft = (120, 200)
        s.update_rect()
        self.sprites.add(s)
        self.textsprites.append(TextSprite(
            self.font, "Pick up all the crystals", black,
            left=240, top=200))

        s = Asteroid(diameter=32)
        s.gamerect.topleft = (120, 280)
        s.update_rect()
        self.sprites.add(s)
        asteroidgamebounds = pygame.Rect(240, 340, 960 - 120 - 120, 160)
        self.asteroids = pygame.sprite.Group([
            Asteroid(diameter=64,
                     dx=1.5,
                     dy=1.0,
                     top=asteroidgamebounds.top,
                     left=asteroidgamebounds.left,
                     area=asteroidgamebounds),
            Asteroid(diameter=80,
                     dx=2.5,
                     dy=-1,
                     top=asteroidgamebounds.top + 20,
                     left=asteroidgamebounds.left + 400,
                     area=asteroidgamebounds),
            Asteroid(diameter=40,
                     dx=-1,
                     dy=-3,
                     top=asteroidgamebounds.top + 40,
                     left=asteroidgamebounds.left + 600,
                     area=asteroidgamebounds)])
        self.textsprites.append(
            TextSprite(
                self.font,
                "Avoid the bouncing asteroids. Hit one and it's game over.",
                black, left=240, top=280))

        s = ShieldPowerup()
        s.gamerect.topleft = (120, 500)
        s.update_rect()
        self.sprites.add(s)
        self.textsprites.append(TextSprite(
            self.font,
            "Pick up a shield to pass through asteroids for a few seconds",
            black, left=240, top=500))

        s = SlowPowerup()
        s.gamerect.topleft = (120, 580)
        s.update_rect()
        self.sprites.add(s)
        self.textsprites.append(TextSprite(
            self.font,
            "Pick up a clock to slow asteroids for a few seconds",
            black, left=240, top=580))

        s = ReactionTimePrompt(image="triangle.png")
        s.gamerect.topleft = (105, 640)
        s.update_rect()
        self.sprites.add(s)
        self.textsprites.append(TextSprite(
            self.font,
            "Press z when you see a triangle",
            black, left=240, top=660))

        s = ReactionTimePrompt(image="square.png")
        s.gamerect.topleft = (105, 720)
        s.update_rect()
        self.sprites.add(s)
        self.textsprites.append(TextSprite(
            self.font,
            "Press x when you see a square",
            black, left=240, top=740))

        if self.click_to_continue:
            self.textsprites.append(TextSprite(
                self.font_big, "Click To Begin", red,
                centerx=virtualdisplay.GAME_AREA.width / 2,
                bottom=virtualdisplay.GAME_AREA.height - 50))

        self.first_update = True

    def draw(self):
        # draw background
        self.screen.blit(self.blackbackground, (0, 0))
        # draw all text blocks:
        for textsprite in self.textsprites:
            textsprite.draw(self.screen)
        self.sprites.draw(self.screen)
        self.asteroids.draw(self.screen)

    def update_frontmost(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count,
                         reactionlogger):
        if self.first_update:
            self.first_update = False
            # play music during the instructions at specified volume:
            unmute_music()

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                if self.click_to_continue:
                    # position cursor at the center
                    pygame.mouse.set_pos([
                        virtualdisplay.screenarea.centerx,
                        virtualdisplay.screenarea.centery])
                    # end the instructions screen:
                    self.screenstack.pop()
                    # game.py will switch to gameplay
            elif event.type is MOUSEBUTTONUP:
                pass

        # update asteroid positions
        for asteroid in self.asteroids:
            asteroid.update(millis)


class LevelCompletedOverlayScreen(GameScreen):
    """
    Show a "Level Complete" message on top of the gameplay screen, pausing the
    gameplay while this screen is visible.

    This screen automatically ends after a delay.
    """

    def __init__(self, screen, gamescreenstack):
        GameScreen.__init__(self, screen, gamescreenstack)
        self.name = 'level_complete'
        self.opaque = False
        self.screenarea = self.screen.get_rect()
        self.font = load_font('Ubuntu-M.ttf', 36)
        self.text = self.font.render("Level Completed", 1, (250, 10, 10))
        self.textpos = self.text.get_rect(
            centerx=self.screenarea.width / 2, centery=self.screenarea.height / 2)
        self.elapsedmillis = 0

    def draw(self):
        self.screen.blit(self.text, self.textpos)

    def close(self):
        """Close this screen by removing it from the screen stack"""
        if (len(self.screenstack) > 1
                and isinstance(self.screenstack[-2], AsteroidImpactGameplayScreen)):
            # advance to next level
            self.screenstack[-2].advance_level()
        if (len(self.screenstack) > 1
                and isinstance(self.screenstack[-2], AsteroidImpactInfiniteGameplayScreen)):
            # advance to next level
            self.screenstack[-2].advance_level()
        # remove 'level completed' screen
        topscreen = self.screenstack.pop()

    def update_frontmost(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count,
                         reactionlogger):
        self.elapsedmillis += millis

        if self.elapsedmillis >= 1000:
            self.close()

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                # self.close()
                pass
            elif event.type is MOUSEBUTTONUP:
                pass


class GameOverOverlayScreen(GameScreen):
    """
    Show a "Game Over" message on top of the gameplay screen, pausing the
    gameplay while this screen is visible.

    This screen automatically ends after a delay.
    """

    def __init__(self, screen, gamescreenstack):
        GameScreen.__init__(self, screen, gamescreenstack)
        self.name = 'game_over'
        self.opaque = False
        self.screenarea = self.screen.get_rect()
        self.font = load_font('Ubuntu-M.ttf', 36)
        self.text = self.font.render("You Died!", 1, (250, 10, 10))
        self.textpos = self.text.get_rect(
            centerx=self.screenarea.width / 2, centery=self.screenarea.height / 2)
        self.elapsedmillis = 0

    def draw(self):
        self.screen.blit(self.text, self.textpos)
        pass

    def close(self):
        """Close this screen by removing it from the screen stack"""
        if (len(self.screenstack) > 1
                and isinstance(self.screenstack[-2], AsteroidImpactGameplayScreen)):
            # reload same level
            self.screenstack[-2].setup_level()
        if (len(self.screenstack) > 1
                and isinstance(self.screenstack[-2], AsteroidImpactInfiniteGameplayScreen)):
            # reload same level
            self.screenstack[-2].setup_level(first=False, died_previously=True)
        # remove 'game over' screen
        topscreen = self.screenstack.pop()

    def update_frontmost(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count,
                         reactionlogger):
        self.elapsedmillis += millis

        if self.elapsedmillis >= 1000:
            self.close()

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                pass
                # self.close()
            elif event.type is MOUSEBUTTONUP:
                pass


def circularspritesoverlap(a, b):
    """
    Returns true if two circular game sprites overlap.

    The sprite overlap is checked using their ``gamerect`` to find the sprite position and diameter.
    """
    x1 = a.gamerect.centerx
    y1 = a.gamerect.centery
    d1 = a.gamerect.width
    x2 = b.gamerect.centerx
    y2 = b.gamerect.centery
    d2 = b.gamerect.width
    # x1, y1, d1, x2, y2, d2
    return ((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1)) < (.25 * (d1 + d2) * (d1 + d2))


def make_powerup(powerup_dict):
    """
    returns a new powerup of the type specified in the level JSON by checking the ``"type"`` key in powerup_dict.
    """
    # copy so that removing 'type' doesn't change original
    powerup_dict = dict(powerup_dict)
    powerup_type = powerup_dict.pop('type')
    if powerup_type == 'shield':
        return ShieldPowerup(**powerup_dict)
    if powerup_type == 'slow':
        return SlowPowerup(**powerup_dict)
    if powerup_type == 'none':
        return NonePowerup(**powerup_dict)
    print('ERROR: Unknown type of powerup in level: ', powerup_type)


class AsteroidImpactGameplayScreen(GameScreen):
    """
    Gameplay logic for the Asteroid Impact game.
    """

    def __init__(self,
                 screen,
                 screenstack,
                 levellist,
                 reaction_prompts_settings,
                 game_element_opacity=255,
                 **kwargs):
        GameScreen.__init__(self, screen, screenstack)

        if game_element_opacity > 255:
            game_element_opacity = 255
        if game_element_opacity < 1:
            game_element_opacity = 1
        self.game_element_opacity = game_element_opacity

        self.name = 'gameplay'
        self.blackbackground = pygame.Surface(self.screen.get_size())
        self.blackbackground = self.blackbackground.convert()
        self.blackbackground.fill((0, 0, 0))

        self.gamebackground = load_image('background4x3.jpg', size=virtualdisplay.screenplayarea.size)
        # draw game background on black background to only have to draw black/game once per frame:
        self.blackbackground.blit(self.gamebackground, virtualdisplay.screenarea.topleft)

        # draw outline around game area
        # pygame.draw.rect(self.blackbackground, (250, 250, 250), virtualdisplay.screenplayarea, 1)

        status_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 64, 64)).height
        status_font = load_font('Ubuntu-M.ttf', status_font_size)
        status_color = (250, 250, 10)

        notice_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 64, 64)).height
        notice_font = load_font('Ubuntu-M.ttf', notice_font_size)
        notice_color = (250, 250, 10)

        self.status_asteroids_textsprite = TextSprite(
            status_font, "000/000", status_color,
            x=64,
            bottom=960)

        self.status_time_textsprite = TextSprite(
            status_font, "0.00s", status_color,
            x=virtualdisplay.GAME_AREA.width / 2,
            bottom=960)

        self.notice_textsprite = TextSprite(
            notice_font, '', notice_color,
            centerx=virtualdisplay.GAME_AREA.centerx,
            centery=virtualdisplay.GAME_AREA.centery)

        self.textsprites = [
            self.status_asteroids_textsprite,
            self.status_time_textsprite,
            self.notice_textsprite]

        self.sound_death = load_sound('DeathFlash.wav')

        # Display The Background
        self.screen.blit(self.blackbackground, (0, 0))
        self.level_list = levellist
        if len(self.level_list) == 0:
            print('ERROR: Level list is empty')
            raise QuitGame
        self.level_index = 0
        self.level_attempt = -1
        self.setup_level()

        self.first_update = True

        # reaction time prompts are independent of level list
        # load their settings from step JSON
        self.reaction_prompts = ReactionTimePromptGroup(reaction_prompts_settings)

    def setup_level(self):
        """Setup for the current level"""
        leveldetails = self.level_list[self.level_index]
        self.level_millis = -2000  # for the 'get ready' and level countdown

        self.cursor = Cursor(game_bounds=virtualdisplay.GAME_PLAY_AREA)
        self.target_positions = leveldetails['target_positions']
        self.target_index = 0
        self.target = Target(
            diameter=32,
            left=self.target_positions[0][0],
            top=self.target_positions[0][1])
        self.asteroids = [Asteroid(**d) for d in leveldetails['asteroids']]
        self.powerup_list = [make_powerup(d) for d in leveldetails['powerup_list']]
        self.powerup = self.powerup_list[0]
        self.next_powerup_list_index = 1 % len(self.powerup_list)
        self.mostsprites = pygame.sprite.OrderedUpdates(
            self.asteroids + [self.cursor, self.target])
        self.powerupsprites = pygame.sprite.Group()
        if self.powerup.image:
            self.powerupsprites.add(self.powerup)
        self.update_status_text()
        self.update_notice_text(self.level_millis, -10000)
        self.level_attempt += 1
        self.level_first_update = True

    def advance_level(self):
        """Advance the current level to the next in the list"""
        self.level_index = (self.level_index + 1) % len(self.level_list)
        self.level_attempt = -1
        self.setup_level()

    def update_status_text(self):
        """Update numbers in status text sprites"""
        self.status_asteroids_textsprite.set_text(
            '%d/%d collected' % (self.target_index, len(self.target_positions)))
        self.status_time_textsprite.set_text('%2.2f' % (self.level_millis / 1000.))

    def update_notice_text(self, level_millis, oldlevel_millis):
        """Update level countdown text"""
        #                   Get Ready -
        # -1000... -0000    Set
        # -0000 ... +500    Go
        # +500 ... death    [nothing]
        if oldlevel_millis < -2000 and -2000 <= level_millis:
            self.notice_textsprite.set_text('Get Ready')
        if oldlevel_millis < -1000 and -1000 <= level_millis:
            self.notice_textsprite.set_text('Set')
        if oldlevel_millis < 0 and 0 <= level_millis:
            self.notice_textsprite.set_text('Go')
        if oldlevel_millis < 500 and 500 <= level_millis:
            self.notice_textsprite.set_text('')

    def update_always(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count, reactionlogger):
        # The reaction time prompts run always, independent of the game state.
        # This allows them to be triggered externally, even when the player is
        # on a "level completed" or "you died" screen.
        self.reaction_prompts.update(millis, logrowdetails, reactionlogger, frame_outbound_triggers, events,
                                     step_trigger_count)

    def update_frontmost(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count,
                         reactionlogger):
        """Run per-frame game logic"""

        if self.level_first_update:
            self.level_first_update = False
            frame_outbound_triggers.append('game_level_begin')

        oldmlevelillis = self.level_millis
        self.level_millis += millis

        if self.first_update:
            self.first_update = False
            # play music during the instructions at specified volume:
            unmute_music()

        levelstate = 'countdown' if self.level_millis < 0 else 'playing'

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                pass
            elif event.type is MOUSEBUTTONUP:
                pass

        self.update_notice_text(self.level_millis, oldmlevelillis)
        if self.level_millis < 0:
            # get ready countdown
            # only update asteroids, cursor
            self.mostsprites.update(millis)
        else:
            # game is running (countdown to level start is over)
            self.mostsprites.update(millis)

            # update powerups
            # if current power-up has been used completely:
            if self.powerup.used:
                # switch to and get ready next one:
                self.powerup = self.powerup_list[self.next_powerup_list_index]
                self.powerup.used = False
                self.powerupsprites.empty()
                if self.powerup.image:
                    self.powerupsprites.add(self.powerup)
                self.next_powerup_list_index = \
                    (1 + self.next_powerup_list_index) % len(self.powerup_list)
                # print 'new available powerup is', self.powerup, 'at', self.powerup.gamerect
            self.powerup.update(millis, frame_outbound_triggers, self.cursor, self.asteroids)

            # Check target collision:
            if circularspritesoverlap(self.cursor, self.target):
                # hit.
                self.target.pickedup()
                # increment counter of targets hit
                self.target_index += 1

                frame_outbound_triggers.append('game_crystal_collected')

                if self.target_index >= len(self.target_positions):
                    print('completed level')
                    levelstate = 'completed'
                    self.screenstack.append(LevelCompletedOverlayScreen(
                        self.screen, self.screenstack))
                    frame_outbound_triggers.append('game_level_complete')
                else:
                    # position for next crystal target:
                    self.target.gamerect.left = self.target_positions[self.target_index][0]
                    self.target.gamerect.top = self.target_positions[self.target_index][1]
                    self.target.update_rect()

            # Check powerup collision
            if self.powerup != None \
                    and circularspritesoverlap(self.cursor, self.powerup) \
                    and not self.powerup.active \
                    and not self.powerup.used:
                print('activating powerup:', self.powerup)
                self.powerup.activate(self.cursor, self.asteroids, frame_outbound_triggers)

            # Check asteroid collision:
            for asteroid in self.asteroids:
                if circularspritesoverlap(self.cursor, asteroid):
                    # todo: find a cleaner way to have the shield powerup do this work:
                    if not (self.powerup != None
                            and isinstance(self.powerup, ShieldPowerup)
                            and self.powerup.active):
                        self.sound_death.play()
                        print('dead', self.cursor.rect.left, self.cursor.rect.top)
                        levelstate = 'dead'
                        self.screenstack.append(
                            GameOverOverlayScreen(self.screen, self.screenstack))
                        frame_outbound_triggers.append('game_death')
                        break

        self.update_status_text()
        logrowdetails['level_millis'] = self.level_millis
        logrowdetails['level_name'] = self.level_list[self.level_index]['level_name']
        logrowdetails['level_attempt'] = self.level_attempt + 1
        logrowdetails['level_state'] = levelstate

        logrowdetails['targets_collected'] = self.target_index
        logrowdetails['target_x'] = self.target.gamerect.centerx
        logrowdetails['target_y'] = self.target.gamerect.centery

        # active powerup (none, shield, slow)
        logrowdetails['active_powerup'] = 'none'
        if self.powerup and self.powerup.active:
            logrowdetails['active_powerup'] = self.powerup.type

        # on-screen powerup (these get weird when active)
        logrowdetails['powerup_x'] = self.powerup.gamerect.centerx
        logrowdetails['powerup_y'] = self.powerup.gamerect.centery
        logrowdetails['powerup_diameter'] = self.powerup.gamediameter
        logrowdetails['powerup_type'] = self.powerup.type

        logrowdetails['cursor_x'] = self.cursor.gamerect.centerx
        logrowdetails['cursor_y'] = self.cursor.gamerect.centery

        for i, asteroid in enumerate(self.asteroids):
            # asteroid columns
            prefix = 'asteroid_%d_' % (i + 1)
            logrowdetails[prefix + 'centerx'] = asteroid.gamerect.centerx
            logrowdetails[prefix + 'centery'] = asteroid.gamerect.centery
            logrowdetails[prefix + 'diameter'] = asteroid.gamediameter

    def after_close(self, logrowdetails, reactionlogger, surveylogger):
        # halt all pending sounds
        for s in self.mostsprites:
            s.stop_audio()
        for s in self.powerupsprites:
            s.stop_audio()
        for s in self.reaction_prompts:
            s.step_end_deactivate(logrowdetails, reactionlogger)

    def draw(self):
        """draw game to ``self.screen``"""
        self.screen.blit(self.blackbackground, (0, 0))

        self.mostsprites.draw(self.screen)
        self.powerupsprites.draw(self.screen)
        self.reaction_prompts.draw(self.screen)

        if self.game_element_opacity < 255:
            # overlay the background over game elements to easily simulate dropping their opacity:
            self.blackbackground.set_alpha(255 - self.game_element_opacity)
            self.screen.blit(self.blackbackground, (0, 0))
            self.blackbackground.set_alpha(None)  # another way to be opaque

        # draw all text blocks:
        for textsprite in self.textsprites:
            textsprite.draw(self.screen)


class AsteroidImpactInfiniteLevelMaker(object):
    '''
    List-like class that generates new levels as they are requested
    '''

    def __init__(
            self,
            level_templates_list,
            start_level=0.0,
            level_completion_increment=1.0,
            level_death_decrement=1.0,
            continuous_asteroids_on_same_level=False,
            adaptive_asteroid_size_locked_to_initial=False,
            show_advance_countdown=False,
            multicolor_crystal_scoring=False,
            multicolor_crystal_numbers=[-1],
            **kwargs_ignored):
        print(start_level, level_completion_increment, level_death_decrement)
        self.level_score = start_level
        self.level_completion_increment = level_completion_increment
        self.level_death_decrement = level_death_decrement
        self.continuous_asteroids_on_same_level = continuous_asteroids_on_same_level
        self.adaptive_asteroid_size_locked_to_initial = adaptive_asteroid_size_locked_to_initial
        self.show_advance_countdown = show_advance_countdown
        self.multicolor_crystal_scoring = multicolor_crystal_scoring

        # validate multicolor_crystal_numbers
        self.multicolor_crystal_numbers = multicolor_crystal_numbers
        if self.multicolor_crystal_scoring:
            if not self.multicolor_crystal_numbers or self.multicolor_crystal_numbers[0] == -1:
                # only the first color
                self.multicolor_crystal_numbers = [1]
        else:
            # only the original color when not using multicolor scoring
            self.multicolor_crystal_numbers = [-1]

        self.level_args_list = level_templates_list
        self.level_used_count_list = [0] * len(level_templates_list)

        self.level_index_previous = -1

    # must act like a list?
    def __len__(self):
        return 2000000000

    def __getitem__(self, index):
        level_index = int(self.level_score + 0.001)  # add some fudge to round correctly
        level_index = min(level_index, len(self.level_args_list) - 1)
        level_args = self.level_args_list[level_index]
        print('generating new level for index', level_index, ' # times previously generated:',
              self.level_used_count_list[level_index])

        # create random from level args
        def make_level_hash(
                seed=None,
                target_count=5,
                asteroid_count=3,
                asteroid_sizes='large',
                asteroid_speeds='slow',
                powerup_count=10,
                powerup_initial_delay=0.0,
                powerup_delay=1.0,
                powerup_types='all'):
            if seed != None:
                return seed
            # convert arguments that might be lists to tuples:
            if isinstance(asteroid_sizes, list): asteroid_sizes = tuple(asteroid_sizes)
            if isinstance(asteroid_speeds, list): asteroid_speeds = tuple(asteroid_speeds)
            if isinstance(powerup_types, list): powerup_types = tuple(powerup_types)
            return hash((
                target_count,
                asteroid_count,
                asteroid_speeds,
                asteroid_sizes,
                powerup_count,
                powerup_initial_delay,
                powerup_types))

        level_hash = make_level_hash(**self.level_args_list[level_index])

        # advance random some multiple of times of # level has been played
        rnd = random.Random(level_hash)
        for i in range(100 * self.level_used_count_list[level_index]):
            rnd.random()

        level_args = self.level_args_list[level_index].copy()
        level_args['rnd'] = rnd
        target_count_real = level_args['target_count']
        if self.multicolor_crystal_scoring:
            # override target count so we get enough to show in multiple colors and having them disappear
            level_args['target_count'] = 5 * (level_args['target_count'] + len(self.multicolor_crystal_numbers))
        level = make_level(**level_args)
        self.level_used_count_list[level_index] += 1
        level['level_name'] = 'dynamic-' + str(level_index)

        # reset target count
        level_args['target_count'] = target_count_real
        level['target_count'] = target_count_real

        level_target_list = []
        for p in level['target_positions']:
            level_target_list.append(dict(left=p[0],
                                          top=p[1],
                                          diameter=TARGET_SIZE,
                                          color=rnd.choice(self.multicolor_crystal_numbers)))
        level['level_target_list'] = level_target_list

        # debug print
        # print 'previous level_index', self.level_index_previous, 'new', level_index
        level['level_index_changed_from_previous'] = (level_index != self.level_index_previous)

        self.level_index_previous = level_index

        return level

    def level_completed(self, level_millis, frame_outbound_triggers):
        "Increment level score based on level completion"
        level_index_old = int(self.level_score + 0.001)  # add some fudge to round correctly

        # increment difficulty
        self.level_score += self.level_completion_increment
        # keep from going too high
        self.level_score = min(max(0.0, self.level_score), len(self.level_args_list) + 1)

        level_index_new = int(self.level_score + 0.001)  # add some fudge to round correctly
        if level_index_old < level_index_new:
            frame_outbound_triggers.append('adaptive_difficulty_increase')

    def level_death(self, level_millis, frame_outbound_triggers):
        "Reduce level score based on level failure"

        level_index_old = int(self.level_score + 0.001)  # add some fudge to round correctly

        # decrement difficulty
        self.level_score -= self.level_death_decrement
        # keep at or above 0
        self.level_score = min(max(0.0, self.level_score), len(self.level_args_list) + 1)

        level_index_new = int(self.level_score + 0.001)  # add some fudge to round correctly
        if level_index_new < level_index_old:
            frame_outbound_triggers.append('adaptive_difficulty_decrease')


class AsteroidImpactInfiniteGameplayScreen(GameScreen):
    """
    Gameplay logic for the Asteroid Impact game.
    """

    def __init__(
            self,
            screen,
            screenstack,
            level_templates_list,
            reaction_prompts_settings,
            game_element_opacity=255,
            game_globals=None,
            **kwargs):
        GameScreen.__init__(self, screen, screenstack)
        self.name = 'gameplay-adaptive'
        self.step_kwargs = kwargs
        self.game_globals = game_globals
        self.timer = 0

        # init high score if there is none
        if 'multicolor_high_score' not in self.game_globals:
            game_globals['multicolor_high_score'] = 0

        if game_element_opacity > 255:
            game_element_opacity = 255
        if game_element_opacity < 1:
            game_element_opacity = 1
        self.game_element_opacity = game_element_opacity

        # multicolor scoring properties
        self.multicolor_crystal_scoring = False
        if 'multicolor_crystal_scoring' in kwargs:
            self.multicolor_crystal_scoring = kwargs['multicolor_crystal_scoring']

        self.multicolor_crystal_num_showing = 1
        self.multicolor_crystal_lifetime_ms = None
        # score table to find score as player collects crystal
        # row: current crystal color
        # column: previously collected crystal color. If no previous, use 6th cell.
        self.multicolor_crystal_score_table = [[0] * 6] * 5

        if self.multicolor_crystal_scoring:
            # load multicolor-crystal-scoring specific options:
            if 'multicolor_crystal_num_showing' in kwargs:
                self.multicolor_crystal_num_showing = kwargs['multicolor_crystal_num_showing']

            if 'multicolor_crystal_lifetime_ms' in kwargs:
                self.multicolor_crystal_lifetime_ms = kwargs['multicolor_crystal_lifetime_ms']

            if 'multicolor_crystal_score_table' in kwargs:
                self.multicolor_crystal_score_table = kwargs['multicolor_crystal_score_table']
            else:
                # all tens
                self.multicolor_crystal_score_table = [[10 for s in row] for row in self.multicolor_crystal_score_table]

        self.multicolor_crystal_negative_score_buzzer = False
        if 'multicolor_crystal_negative_score_buzzer' in kwargs:
            self.multicolor_crystal_negative_score_buzzer = kwargs['multicolor_crystal_negative_score_buzzer']

        self.blackbackground = pygame.Surface(self.screen.get_size())
        self.blackbackground = self.blackbackground.convert()
        self.blackbackground.fill((0, 0, 0))

        self.gamebackground = load_image('background4x3.jpg', size=virtualdisplay.screenplayarea.size)
        # draw gamebackground on blackbackground to only have to draw black/game once per frame:
        self.blackbackground.blit(self.gamebackground, virtualdisplay.screenarea.topleft)
        try:
            self.mondrian = load_image('mond.png', size=virtualdisplay.screenarea.size)
        except:
            self.mondrian = None
        self.blank = load_image("transparent.png", size=virtualdisplay.screenarea.size)
        self.overlay = None

        status_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 64, 64)).height
        status_font = load_font('Ubuntu-M.ttf', status_font_size)
        status_color = (250, 250, 10)

        notice_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 64, 64)).height
        notice_font = load_font('Ubuntu-M.ttf', notice_font_size)
        notice_color = (250, 250, 10)

        self.status_asteroids_textsprite = TextSprite(
            status_font, "000/000", status_color,
            x=64,
            bottom=960)

        self.status_time_textsprite = TextSprite(
            status_font, "0.00s", status_color,
            x=virtualdisplay.GAME_AREA.width / 2,
            bottom=960)

        self.status_score_textsprite = TextSprite(
            status_font, "Score: 00000", status_color,
            x=20,
            bottom=960)

        self.status_highscore_textsprite = TextSprite(
            status_font, "High Score: 00000", status_color,
            x=virtualdisplay.GAME_AREA.width / 2,
            bottom=960)

        self.notice_textsprite = TextSprite(
            notice_font, '', notice_color,
            centerx=virtualdisplay.GAME_AREA.centerx,
            centery=virtualdisplay.GAME_AREA.centery)

        # positioned on top of picked up crystal to show score change
        self.score_increment_textsprite = TextSprite(
            status_font, '', status_color,
            x=0, y=0)
        # timer to disappear text after delay
        self.score_increment_elapsed_ms = 10000

        self.textsprites = [
            self.status_asteroids_textsprite,
            self.status_time_textsprite,
            self.status_score_textsprite,
            self.status_highscore_textsprite,
            self.score_increment_textsprite,
            self.notice_textsprite]

        self.sound_death = load_sound('DeathFlash.wav')

        # Display The Background
        self.screen.blit(self.blackbackground, (0, 0))
        if len(level_templates_list) == 0:
            print('ERROR: Level list is empty')
            raise QuitGame
        levellist = AsteroidImpactInfiniteLevelMaker(level_templates_list, **kwargs)
        self.level_list = levellist
        self.level_attempt = -1
        self.setup_level(first=True)

        self.first_update = True

        # reaction time prompts are independent of level list
        # load their settings from step JSON
        self.reaction_prompts = ReactionTimePromptGroup(reaction_prompts_settings)

        self.overlay = Overlay()

    def setup_level(self, first=True, died_previously=False):
        """Setup for the current level"""
        self.died_previously = died_previously
        self.current_level = self.level_list['unused']
        self.show_countdown = (
                first
                or died_previously
                or (self.level_list.show_advance_countdown and self.current_level['level_index_changed_from_previous']))
        print('self.show_countdown', self.show_countdown)
        self.level_millis = -2000 if (self.show_countdown) else 0  # for the 'get ready' and level countdown

        # resetting the cursor flashes it in top left
        # this fixes typical case of advancing to next level, but it still happens
        # when you die
        if first:
            self.cursor = Cursor(game_bounds=virtualdisplay.GAME_PLAY_AREA)

        self.simultaneous_targets = self.multicolor_crystal_num_showing
        self.targets_collected = 0
        self.target_collection_target = self.current_level['target_count']
        self.target_next_index = 0

        # all target sprites are created/positioned at load time! just not shown
        target_list_new = []
        for t in self.current_level['level_target_list']:
            sprite = ScoredTarget(diameter=t['diameter'],
                                  left=t['left'],
                                  top=t['top'],
                                  # when acting like "classic" behavior, use 'crystal.png'
                                  imagefile='Crystal_%i.png' % t['color'] if t['color'] >= 1 else 'crystal.png',
                                  number=t['color'],
                                  lifetime_millis_max=self.multicolor_crystal_lifetime_ms,
                                  play_buzzer_on_negative_score=self.multicolor_crystal_negative_score_buzzer)
            target_list_new.append(sprite)

        if first or died_previously:
            # I'm not sure the LayeredDirty group is ordered so its its own thing
            self.target_list = target_list_new
        else:
            # include existing active targets in front of new list
            self.target_list = [t for t in self.target_list if t.active]
            self.target_list.extend(target_list_new)
        self.targetsprites = pygame.sprite.LayeredDirty(self.target_list)
        self.show_required_targets()

        if first or died_previously:
            self.score = 0

        if first:
            self.asteroids = [Asteroid(**d) for d in self.current_level['asteroids']]
            self.target_previously_collected_number = 'x'
        else:
            if (self.current_level['level_index_changed_from_previous']
                    or (not self.level_list.continuous_asteroids_on_same_level)):
                # update asteroid speeds and sizes:
                new_asteroids = [Asteroid(**d) for d in self.current_level['asteroids']]
                # transition existing asteroid list into new asteroid list
                prev_asteroid_count = len(self.asteroids)
                if (len(new_asteroids) < len(self.asteroids)):
                    # reduce asteroid count by scaling down size. They are removed in update()
                    for i in range(len(new_asteroids), len(self.asteroids)):
                        disappearing_asteroid = self.asteroids[i]
                        disappearing_asteroid.gamediameternew_start_diameter = disappearing_asteroid.gamediameter
                        disappearing_asteroid.gamediameternew_end_diameter = 1
                        disappearing_asteroid.gamediameternew_transition_duration_millis = 1000
                        disappearing_asteroid.gamediameternew_transition_remaining_millis = 1000
                        disappearing_asteroid.dxnew = disappearing_asteroid.dx
                        disappearing_asteroid.dynew = disappearing_asteroid.dy
                elif (len(self.asteroids) < len(new_asteroids)):
                    # duplicate asteroids to increase count
                    for i in range(len(self.asteroids), len(new_asteroids)):
                        new_asteroid = Asteroid()
                        new_asteroid.copy_from(self.asteroids[i % prev_asteroid_count])
                        self.asteroids.append(new_asteroid)

                for i, newasteroid in enumerate(new_asteroids):
                    # set up transition to new size, angle
                    asteroid = self.asteroids[i]
                    if self.level_list.adaptive_asteroid_size_locked_to_initial and i < prev_asteroid_count:
                        # keep same size
                        asteroid.gamediameternew_start_diameter = asteroid.gamediameter
                        asteroid.gamediameternew_end_diameter = asteroid.gamediameter
                        asteroid.gamediameternew_transition_duration_millis = 50
                        asteroid.gamediameternew_transition_remaining_millis = 50
                    else:
                        # transition to new size
                        asteroid.gamediameternew_start_diameter = asteroid.gamediameter
                        asteroid.gamediameternew_end_diameter = newasteroid.gamediameter
                        asteroid.gamediameternew_transition_duration_millis = 2000
                        asteroid.gamediameternew_transition_remaining_millis = 2000
                    asteroid.dxnew = newasteroid.dx
                    asteroid.dynew = newasteroid.dy

        if first:
            prevpowerup = None
        else:
            prevpowerup = self.powerup
        if died_previously:
            prevpowerup = None

        self.powerup_list = [make_powerup(d) for d in self.current_level['powerup_list']]
        self.powerup = self.powerup_list[0]
        self.next_powerup_list_index = 1 % len(self.powerup_list)
        if not first and not died_previously and prevpowerup.active:
            # keep it around
            self.powerup_list.insert(0, prevpowerup)
            self.powerup = prevpowerup
        self.mostsprites = pygame.sprite.LayeredDirty(self.asteroids + [self.cursor])
        self.powerupsprites = pygame.sprite.Group()
        if self.powerup.image:
            self.powerupsprites.add(self.powerup)
        self.update_status_text()
        self.update_notice_text(self.level_millis, -10000)
        self.level_attempt += 1
        self.level_first_update = True

    def advance_level(self):
        """Advance the current level to the next in the list"""
        self.level_attempt = -1
        self.setup_level(first=False)

    def update_status_text(self):
        """Update numbers in status text sprites"""

        if self.multicolor_crystal_scoring:
            self.status_asteroids_textsprite.set_text('')
            self.status_time_textsprite.set_text('')
            self.status_score_textsprite.set_text('Score: %05d' % self.score)
            self.status_highscore_textsprite.set_text('High Score: %05d' % self.game_globals['multicolor_high_score'])
        else:
            self.status_asteroids_textsprite.set_text(
                '%d/%d collected' % (self.targets_collected, self.target_collection_target))
            self.status_time_textsprite.set_text('%2.2f' % (self.level_millis / 1000.))
            self.status_score_textsprite.set_text('')
            self.status_highscore_textsprite.set_text('')

    def update_notice_text(self, level_millis, oldlevel_millis):
        """Update level countdown text"""
        #                   Get Ready -
        # -1000... -0000    Set
        # -0000 ... +500    Go
        # +500 ... death    [nothing]
        if self.show_countdown:
            if oldlevel_millis < -2000 and -2000 <= level_millis:
                self.notice_textsprite.set_text('Get Ready')
            if oldlevel_millis < -1000 and -1000 <= level_millis:
                self.notice_textsprite.set_text('Set')
            if oldlevel_millis < 0 and 0 <= level_millis:
                self.notice_textsprite.set_text('Go')
            if oldlevel_millis < 500 and 500 <= level_millis:
                self.notice_textsprite.set_text('')

    def update_always(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count, reactionlogger):
        # The reaction time prompts run always, independent of the game state.
        # This allows them to be triggered externally, even when the player is
        # on a "level completed" or "you died" screen.
        score_changes = self.reaction_prompts.update(millis, logrowdetails, reactionlogger, frame_outbound_triggers,
                                                     events, step_trigger_count)

        if self.multicolor_crystal_scoring:
            for score_change in score_changes:
                self.score += score_change['change']

                # show score change
                self.score_increment_elapsed_ms = 0
                self.score_increment_textsprite.set_position(
                    centerx=score_change['centerx'],
                    centery=score_change['centery'])
                self.score_increment_textsprite.set_text('{:+n}'.format(score_change['change']))

                # update high score
                if self.game_globals['multicolor_high_score'] < self.score:
                    self.game_globals['multicolor_high_score'] = self.score

    def update_frontmost(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count,
                         reactionlogger):
        """Run per-frame game logic"""

        if self.level_first_update:
            self.level_first_update = False
            frame_outbound_triggers.append('game_level_begin')

        oldlevel_millis = self.level_millis
        self.level_millis += millis

        if self.first_update:
            self.first_update = False
            # play music during the instructions at specified volume:
            unmute_music()

        levelstate = 'countdown' if self.level_millis < 0 else 'playing'

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                pass
            elif event.type is MOUSEBUTTONUP:
                pass

        self.update_notice_text(self.level_millis, oldlevel_millis)
        if self.level_millis < 0:
            # get ready countdown
            # only update asteroids, cursor
            self.mostsprites.update(millis)
            self.targetsprites.update(millis)

            # update shield with zero duration so it continues to follow cursor
            if self.powerup.active:
                self.powerup.update(0, frame_outbound_triggers, self.cursor, self.asteroids)
        else:
            # game is running (countdown to level start is over)
            self.mostsprites.update(millis)
            self.targetsprites.update(millis)

            # update powerups
            # if current power-up has been used completely:
            if self.powerup.used:
                # switch to and get ready next one:
                self.powerup = self.powerup_list[self.next_powerup_list_index]
                self.powerup.used = False
                self.powerupsprites.empty()
                if self.powerup.image:
                    self.powerupsprites.add(self.powerup)
                self.next_powerup_list_index = \
                    (1 + self.next_powerup_list_index) % len(self.powerup_list)
                # print 'new available powerup is', self.powerup, 'at', self.powerup.gamerect
            self.powerup.update(millis, frame_outbound_triggers, self.cursor, self.asteroids)

            # Check target collision:
            for target in self.target_list:
                if target.active and circularspritesoverlap(self.cursor, target):
                    # hit.
                    target.pickedup()

                    # increment score
                    if self.multicolor_crystal_scoring:
                        scoreincrement = 0
                        if isinstance(target.number, int) and target.number > 0:
                            if isinstance(self.target_previously_collected_number, int):
                                # use "nth" column
                                scoreincrement = self.multicolor_crystal_score_table[
                                    target.number - 1][self.target_previously_collected_number - 1]
                            else:
                                # use last column
                                scoreincrement = self.multicolor_crystal_score_table[
                                    target.number - 1][-1]

                        self.score += scoreincrement

                        # show player score change:
                        self.score_increment_elapsed_ms = 0
                        self.score_increment_textsprite.set_position(
                            centerx=target.gamerect.centerx,
                            centery=target.gamerect.centery)
                        self.score_increment_textsprite.set_text('{:+n}'.format(scoreincrement))

                        if self.game_globals['multicolor_high_score'] < self.score:
                            self.game_globals['multicolor_high_score'] = self.score

                    target.pickedup(score=scoreincrement)

                    # increment counter of targets hit
                    self.targets_collected += 1

                    self.target_previously_collected_number = target.number

                    frame_outbound_triggers.append('game_crystal_collected')

                    if self.targets_collected >= self.target_collection_target:
                        print('completed level')
                        levelstate = 'completed'
                        self.level_list.level_completed(self.level_millis, frame_outbound_triggers)
                        self.advance_level()
                        frame_outbound_triggers.append('game_level_complete')
                    else:
                        # showing next target happens at end of update_frontmost() now
                        pass

            # Check powerup collision
            if self.powerup != None \
                    and circularspritesoverlap(self.cursor, self.powerup) \
                    and not self.powerup.active \
                    and not self.powerup.used:
                # print 'activating powerup:', self.powerup
                self.powerup.activate(self.cursor, self.asteroids, frame_outbound_triggers)

            # Check asteroid collision:
            for asteroid in self.asteroids:
                if circularspritesoverlap(self.cursor, asteroid):
                    # todo: find a cleaner way to have the shield powerup do this work:
                    if not (self.powerup != None
                            and isinstance(self.powerup, ShieldPowerup)
                            and self.powerup.active):
                        self.sound_death.play()
                        print('dead', self.cursor.rect.left, self.cursor.rect.top)
                        self.level_list.level_death(self.level_millis, frame_outbound_triggers)
                        levelstate = 'dead'
                        self.screenstack.append(
                            GameOverOverlayScreen(self.screen, self.screenstack))
                        frame_outbound_triggers.append('game_death')

                        if self.powerup.active:
                            self.powerup.deactivate(self.cursor, self.asteroids, frame_outbound_triggers)

                        break

        self.update_status_text()

        self.score_increment_elapsed_ms += millis
        if self.score_increment_elapsed_ms > 350:
            # hide score change
            self.score_increment_textsprite.set_position(
                centerx=-9000,
                centery=-9000)

        logrowdetails['level_millis'] = self.level_millis
        logrowdetails['level_name'] = self.current_level['level_name']
        logrowdetails['level_attempt'] = self.level_attempt + 1
        logrowdetails['level_state'] = levelstate
        # adaptive-specific score:
        logrowdetails['adaptive_level_score'] = self.level_list.level_score

        logrowdetails['targets_collected'] = self.targets_collected
        for t in self.target_list:
            if t.active:
                # record position of first active target:
                logrowdetails['target_x'] = t.gamerect.centerx
                logrowdetails['target_y'] = t.gamerect.centery
                break
        logrowdetails['multicolor_crystal_score'] = self.score

        # active powerup (none, shield, slow)
        logrowdetails['active_powerup'] = 'none'
        if self.powerup and self.powerup.active:
            logrowdetails['active_powerup'] = self.powerup.type

        # on-screen powerup (these get weird when active)
        logrowdetails['powerup_x'] = self.powerup.gamerect.centerx
        logrowdetails['powerup_y'] = self.powerup.gamerect.centery
        logrowdetails['powerup_diameter'] = self.powerup.gamediameter
        logrowdetails['powerup_type'] = self.powerup.type

        logrowdetails['cursor_x'] = self.cursor.gamerect.centerx
        logrowdetails['cursor_y'] = self.cursor.gamerect.centery

        for i, asteroid in enumerate(self.asteroids):
            # asteroid columns
            prefix = 'asteroid_%d_' % (i + 1)
            logrowdetails[prefix + 'centerx'] = asteroid.gamerect.centerx
            logrowdetails[prefix + 'centery'] = asteroid.gamerect.centery
            logrowdetails[prefix + 'diameter'] = asteroid.gamediameter

        # remove shrunken asteroids
        self.asteroids = [asteroid for asteroid in self.asteroids if asteroid.gamediameter >= 10]

        self.show_required_targets()

        self.overlay.update(millis)

    def show_required_targets(self):
        # show targets if not enough are visible
        visible_target_count = len([t for t in self.target_list if t.active])
        next_crystal_lifetime_adjustment = 1.0
        while visible_target_count < self.simultaneous_targets:
            self.target_list[self.target_next_index].activate(life_multiplier=next_crystal_lifetime_adjustment)
            self.target_next_index = (self.target_next_index + 1) % len(self.target_list)
            visible_target_count += 1
            # so more than one crystal shown on same frame don't turn off at exactly the same time
            next_crystal_lifetime_adjustment += 0.3

    def after_close(self, logrowdetails, reactionlogger, surveylogger):
        # halt all pending sounds
        for s in self.mostsprites:
            s.stop_audio()
        for s in self.targetsprites:
            s.stop_audio()
        for s in self.powerupsprites:
            s.stop_audio()
        for s in self.reaction_prompts:
            s.stop_audio()

    def draw(self):
        """draw game to ``self.screen``"""
        self.screen.blit(self.blackbackground, (0, 0))

        self.mostsprites.draw(self.screen)
        self.targetsprites.draw(self.screen)
        self.powerupsprites.draw(self.screen)
        self.reaction_prompts.draw(self.screen)

        if self.game_element_opacity < 255:
            if self.overlay.visible == 1:
                self.overlay.draw(self.screen)
                self.overlay.image.set_alpha(255 - self.game_element_opacity)

        # draw all text blocks:
        for textsprite in self.textsprites:
            textsprite.draw(self.screen)


class ParallelPortTestScreen(GameScreen):
    """
    Parallel Port Test Screen. Display input pins status and toggle output pins by clicking on buttons.
    """

    def __init__(
            self,
            screen,
            gamescreenstack,
            port_address=0x0378):
        GameScreen.__init__(self, screen, gamescreenstack)
        self.name = 'paralleltest'
        self.opaque = True
        self.blackbackground = pygame.Surface(self.screen.get_size())
        self.blackbackground = self.blackbackground.convert()
        self.blackbackground.fill((0, 0, 0))

        self.port_address_data = port_address
        self.port_address_status = port_address + 1
        self.data_byte = 0xFF
        self.status_byte = 0xFF
        self.data_byte = parallelportwrapper.Inp32(self.port_address_data)
        self.status_byte = parallelportwrapper.Inp32(self.port_address_status)

        self.gamebackground = load_image('parallel_debug.png', size=virtualdisplay.screenarea.size)
        # draw gamebackground on blackbackground to only have to draw black/game once per frame:
        self.blackbackground.blit(self.gamebackground, virtualdisplay.screenarea.topleft)

        self.sprites = pygame.sprite.OrderedUpdates()

        self.textsprites = []

        big_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 72, 72)).height
        self.font_big = load_font('Ubuntu-M.ttf', big_font_size)

        self.line_height = 36  # game-space like font size below
        small_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 32, 32)).height
        self.font = load_font('Ubuntu-M.ttf', small_font_size)

        self.digit_line_height = 32
        digit_font_size = virtualdisplay.screenrect_from_gamerect(
            pygame.Rect(0, 0, 32, 32)).height
        self.digit_font = load_font('Ubuntu-M.ttf', digit_font_size)

        self.text_color = (11, 11, 11)  # dark
        self.text_color_option = (127, 127, 127)  # gray
        self.text_color_digit = (11, 11, 11)  # dark
        self.text_color_active_digit = (215, 211, 5)  # yellow

        # init text for prompt
        lines, result_bounds = flow_text(
            "Parallel Port Test.\nClick on buttons to change output pins, or just watch input pins change from other computer.",
            virtualdisplay.GAME_AREA,
            self.font,
            self.text_color,
            self.line_height,
            valign='top')
        self.textsprites += lines

        # used for placement of answers
        bottom_y = virtualdisplay.GAME_AREA.bottom

        # add "Exit" button on bottom
        next_text = "Exit"
        lines, option_bounds = flow_text(
            next_text,
            virtualdisplay.GAME_AREA,
            self.font,
            self.text_color_option,
            self.line_height,
            valign='bottom')
        bottom_y -= (len(lines) + 1) * self.line_height
        self.textsprites += lines

        self.nextbutton = SurveyButton(option_bounds, next_text, lambda b: self.next_button_clicked())

        self.textsprites.append(TextSprite(
            self.font,
            'Port Address: 0x%X' % port_address,
            self.text_color,
            left=0,
            bottom=176))

        self.status_data_value_textsprite = TextSprite(
            self.font,
            'Data value: XYZ (0xQW)',
            self.text_color,
            left=512,
            top=128)
        self.textsprites.append(self.status_data_value_textsprite)

        self.status_status_value_textsprite = TextSprite(
            self.font,
            'Status value: XYZ (0xQW)',
            self.text_color,
            left=192,
            top=768)
        self.textsprites.append(self.status_status_value_textsprite)

        self.update_status_text()

        # create text blocks for data bit
        self.data_bits_sprites = []
        self.data_buttons = []
        for bit in range(8):
            # Data bit
            x = 544 + (64 * (7 - bit))
            y = 288
            self.data_bits_sprites.append(
                [TextSprite(
                    self.digit_font, "0", self.text_color_digit,
                    centerx=x,
                    bottom=y + 16),
                    TextSprite(
                        self.digit_font, "1", self.text_color_active_digit,
                        centerx=x,
                        bottom=y + 16)])
            # add button to toggle output digit
            button_bounds = Rect(x - 32, y - 32, 64, 64)
            data_button = SurveyButton(
                button_bounds,
                "toggle bit %d" % bit,
                lambda b: self.toggle_data_bit_for_button(b))
            self.data_buttons.append(data_button)

        # create text blocks for status bits
        self.status_bits_sprites = [None] * 3
        for bit in [3, 4, 5, 6, 7]:
            x = 224 + (64 * (7 - bit))
            y = 672
            self.status_bits_sprites.append(
                [TextSprite(
                    self.digit_font, "0", self.text_color_digit,
                    centerx=x,
                    bottom=y + 16),
                    TextSprite(
                        self.digit_font, "1", self.text_color_active_digit,
                        centerx=x,
                        bottom=y + 16), ])

        self.first_update = True

    def draw(self):
        # draw background
        self.screen.blit(self.blackbackground, (0, 0))

        # draw buttons
        for b in self.data_buttons:
            b.draw(self.screen)
        self.nextbutton.draw(self.screen)

        # draw all text blocks:
        for textsprite in self.textsprites:
            textsprite.draw(self.screen)

        # Draw data bits:
        for i, dig_list in enumerate(self.data_bits_sprites):
            if self.data_byte & (1 << i):
                dig_list[1].draw(self.screen)
            else:
                dig_list[0].draw(self.screen)

        # Draw status bits:
        for i, dig_list in enumerate(self.status_bits_sprites):
            if dig_list:
                if self.status_byte & (1 << i):
                    dig_list[1].draw(self.screen)
                else:
                    dig_list[0].draw(self.screen)

        self.sprites.draw(self.screen)

    def update_frontmost(self, millis, logrowdetails, frame_outbound_triggers, events, step_trigger_count,
                         reactionlogger):
        if self.first_update:
            self.first_update = False
            # don't play music:
            mute_music()

            pygame.event.set_grab(False)
            pygame.mouse.set_visible(True)

        self.sprites.update(millis)

        for b in self.data_buttons:
            b.update(millis)

        self.nextbutton.update(millis)

        status_byte_new = parallelportwrapper.Inp32(self.port_address_status)
        status_byte_new = status_byte_new & 0xF8  # mask off card-specific low bits
        if self.status_byte != status_byte_new:
            self.status_byte = status_byte_new
            self.update_status_text()

    def toggle_data_bit_for_button(self, button):
        # toggle corresponding bit
        self.data_byte = self.data_byte ^ (1 << self.data_buttons.index(button))
        # update parallel port
        parallelportwrapper.Out32(self.port_address_data, self.data_byte)
        self.update_status_text()

    def next_button_clicked(self):
        # end step
        self.screenstack.pop()

    def update_status_text(self):
        self.status_data_value_textsprite.set_text(
            'Data value: %d (0x%02X)' % (self.data_byte, self.data_byte))
        self.status_status_value_textsprite.set_text(
            'Status value: %d (0x%02X)' % (self.status_byte, self.status_byte))

