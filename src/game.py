# Asteroid Impact (c) Media Neuroscience Lab, Rene Weber
# Authored by Nick Winters
#
# Asteroid Impact is licensed under a
# Creative Commons Attribution-ShareAlike 4.0 International License.
#
# You should have received a copy of the license along with this
# work. If not, see <http://creativecommons.org/licenses/by-sa/4.0/>.
"""
Game loop and screen management for Asteroid Impact game.
"""

# to make python3 porting easier:
# see http://lucumr.pocoo.org/2011/1/22/forwards-compatible-python/
from __future__ import absolute_import, division

import argparse
import json
import os
import random  # step shuffling
from os import path

import pygame
from pygame.locals import *

# >>> 6 / 7
# 1
# >>> from __future__ import division
# >>> 6 / 7
# 1.2857142857142858

try:
    import serial
except ImportError as e:
    print e
    print 'install pyserial, typicially by running `pip install pyserial`'
    print 'otherwise, see https://pypi.python.org/pypi/pyserial'
    import sys

    sys.exit(1)

if not pygame.font:
    print 'Warning, fonts disabled'
if not pygame.mixer:
    print 'Warning, sound disabled'

from screens import (
    AsteroidImpactInstructionsScreen,
    AsteroidImpactInstructionsScreenAlt,
    UserTextScreen,
    SurveyQuestionScreen,
    AsteroidImpactGameplayScreen,
    AsteroidImpactInfiniteGameplayScreen,
    BlackScreen,
    ParallelPortTestScreen,
    QuitGame)
import resources
from sprites import Target
import virtualdisplay
from logger import AsteroidLogger, SurveyLogger, ReactionLogger
import parallelportwrapper

ALL_TRIGGERS = [
    'step_begin',  # on begin of any step
    'game_level_begin',  # in either game mode, when the level begins
    'game_level_complete',  # in either game mode, when the player collects the last diamond
    'game_death',  # in either game mode, when the player touches an asteroid and dies
    'game_crystal_collected',  # in either game mode, when the player collects any diamond
    'game_shield_activate',  # in either game mode, when the player activates a shield
    'game_slow_activate',  # in either game mode, when the player activates the slowdown powerup
    'adaptive_difficulty_increase',  # adaptive, when collecting the last diamond increases to the next level template
    'adaptive_difficulty_decrease'  # adaptive, when dying goes back to an earlier level template
]

# command-line arguments:
parser = argparse.ArgumentParser(description='Run Asteroid Impact game.')
parser.add_argument('--music-volume', type=float, default=1.0,
                    help='Music volume, 1.0 for full.')
parser.add_argument('--effects-volume', type=float, default=1.0,
                    help='Sound effects volume, 1.0 for full.')
parser.add_argument('--display-width', type=int, default=640,
                    help='Width of window or full screen mode.')
parser.add_argument('--display-height', type=int, default=480,
                    help='Height of window or full screen mode.')
parser.add_argument('--window-x', type=int, default=None,
                    help='X position of window.')
parser.add_argument('--window-y', type=int, default=None,
                    help='Y position of window.')
parser.add_argument('--display-mode', choices=['windowed', 'fullscreen'],
                    default='windowed',
                    help='Whether to run windowed or fullscreen.')
parser.add_argument('--list-modes', default=False, const=True, nargs='?',
                    help='List available full screen display modes and exit.')
parser.add_argument('--script-json', type=str, default=None,
                    help=('script.json file listing all steps such as instructions, ' +
                          'gameplay (with levels) and black screens. See ' +
                          'samplescript.json for example.'))
parser.add_argument('--levels-json', type=str, default=None,
                    help=('levellist.json file listing all levels to complete. Ignored ' +
                          'when specifying --script-json'))
parser.add_argument('--single-level-json', type=str, default=None,
                    help=('level.json file to test a single level. Ignored when ' +
                          'specifying --script-json'))
parser.add_argument('--subject-number', type=str, default='',
                    help='Subject number to include in log.')
parser.add_argument('--subject-run', type=str, default='',
                    help='Subject run number to include in the log.')
parser.add_argument('--log-filename', type=str, default=None,
                    help='File to save log CSV file to with per-frame data.')
parser.add_argument('--survey-log-filename', type=str, default=None,
                    help='File to save log CSV file to with survey response data.')
parser.add_argument('--reaction-log-filename', type=str, default=None,
                    help='File to save log CSV file to with reaction prompt data.')
parser.add_argument('--log-overwrite', choices=['true', 'false'], default='false',
                    help='Whether to overwrite pre-existing log files.')
parser.add_argument('--trigger-blink', choices=['true', 'false'], default='false',
                    help='Blink sprite on screen when trigger pulse is received.')
parser.add_argument('--parallel-test-address', type=str, default=None,
                    help='Launch parallel port test interface with specified parallel port data address.')


class GameModeManager(object):
    """
    Follow the instructions to switch between game screens, and levels
    Rather than specifying a single level list, specify a file that has a list of entries
    where each entry specifies the following:

     * Action: Either Instructions, Game, or Black Screen
     * Levels: For the game, the list of level files to play. The player will progress (or
       not) through them in order, and after completing the last level will start again at
       the beginning. Dying will restart the current level.
     * Duration: After this many seconds move to the next step, regardless of what the
       player is doing now.
    """

    def __init__(self, args):
        self.args = args
        # assume error happened if we didn't reach end of __init__
        self.skipgame = True

        self.game_globals = {}

        self.max_asteroid_count = 12

        if self.args.script_json != None:

            with open(self.args.script_json) as f:
                self.script_json = json.load(f)

                # allow script_json to be list of steps
                # or object with 'steps' attribute
                if isinstance(self.script_json, list):
                    self.gamesteps = self.script_json
                    self.script_json = dict(steps=self.gamesteps)
                elif "stepgroups" in self.script_json:
                    self.stepgroups = self.script_json['stepgroups']
                    self.gamesteps = []
                    for stepgroup in self.stepgroups:
                        for step in stepgroup['steps']:
                            self.gamesteps.append(step)
                else:
                    self.gamesteps = []
                    for step in self.script_json['steps']:
                        self.gamesteps.append(step)

            if self.args.levels_json != None or self.args.single_level_json != None:
                print ('Error: When specifying script json you must specify levels in ' +
                       'script, not command-line argument.')
                return
        else:
            levelsjson = 'levels/standardlevels.json'
            if self.args.levels_json != None:
                if not path.exists(self.args.levels_json):
                    print 'Error: Could not find file at "%s"' % self.args.levels_json
                    return
                elif self.args.single_level_json != None:
                    print 'Error: Invalid arguments. Do not specify both --levels-json and --single-level-json'
                    return
                else:
                    levelsjson = self.args.levels_json
            elif self.args.single_level_json != None:
                levelsjson = [self.args.single_level_json]

            # use these steps when the steps aren't specified on the console:
            self.stepgroups = []
            self.gamesteps = [
                dict(action='instructions',
                     duration=None),
                dict(action='game',
                     levels=levelsjson,
                     duration=None)]
            self.script_json = dict(steps=self.gamesteps)

        # load/validate trigger options:
        self.trigger_mode = None
        self.trigger_key = None
        self.trigger_serialport = None
        self.trigger_serialport_byte_value = None
        self.trigger_parallel_port_address = 0x0000
        self.trigger_parallel_port_off_value = 0x00
        self.trigger_parallel_port_on_value = 0x00
        if self.script_json.has_key('trigger_settings'):
            trigger_settings = self.script_json['trigger_settings']
            if trigger_settings['mode'] == 'keyboard':
                self.trigger_mode = 'keyboard'
                keyboard_settings = trigger_settings['keyboard_options']
                self.trigger_key = getattr(pygame, keyboard_settings['trigger_key'], None)
                if not self.trigger_key:
                    print 'trigger_key not found. Please use one of the following'
                    print ', '.join(['"' + s + '"' for s in dir(pygame) if s.startswith('K_')])
                    return
            elif trigger_settings['mode'] == 'serial':
                self.trigger_mode = 'serial'
                serial_settings = trigger_settings['serial_options']

                if not serial_settings.has_key('trigger_byte_value'):
                    print('for serial port, serial_options needs a trigger_byte_value ' +
                          'attribute whose value is the value of the character sent over' +
                          'serial, such as 53 for Ascii "5"')
                self.trigger_serialport_byte_value = int(serial_settings['trigger_byte_value'])

                serialport_options = dict(
                    port=serial_settings['port'],
                    timeout=0.0,
                    baudrate=19200)

                if serial_settings.has_key('bytesize'):
                    serialport_options['bytesize'] = int(serial_settings['bytesize'])
                if serial_settings.has_key('stopbits'):
                    serialport_options['stopbits'] = int(serial_settings['stopbits'])
                if serial_settings.has_key('parity'):
                    parity_options = dict(
                        even=serial.PARITY_EVEN,
                        mark=serial.PARITY_MARK,
                        names=serial.PARITY_NAMES,
                        none=serial.PARITY_NONE,
                        odd=serial.PARITY_ODD,
                        space=serial.PARITY_SPACE)
                    # convert parity option
                    if parity_options.has_key(serial_settings['parity']):
                        serialport_options['parity'] = parity_options[serial_settings['parity']]
                    else:
                        print ('serial_options parity value of "' + serial_settings['parity']
                               + '" was not one of the expected values: ' + json.dumps(parity_options.keys()))
                        return

                # try opening serial port
                try:
                    print 'opening serialport with options:', serialport_options
                    self.trigger_serialport = serial.Serial(**serialport_options)
                    self.trigger_serialport_options = serialport_options
                except serial.SerialException as e:
                    print 'could not open configured serial port'
                    print e
                    print 'exiting.'
                    # exit
                    return

            elif trigger_settings['mode'] == 'parallel':
                self.trigger_mode = 'parallel'
                # required: parallel_options
                if not trigger_settings.has_key('parallel_options'):
                    print 'Invalid script JSON'
                    print 'parallel_options attribute is required for parallel mode trigger_settings'
                    return
                parallel_options = trigger_settings['parallel_options']

                # required: port address
                if not parallel_options.has_key('port_address_hex'):
                    print 'Invalid script JSON'
                    print 'trigger_settings parallel_options must have port_address_hex key'
                    return
                try:
                    self.trigger_parallel_port_address = int(parallel_options['port_address_hex'], 16)
                except ValueError as e:
                    print 'Invalid script JSON'
                    print 'trigger_settings parallel_options port_address_hex must be valid base-16 number'
                    print e
                    return

                # required: ["inactive"] value for status port
                if not parallel_options.has_key('common_status_value_hex'):
                    print 'Invalid script JSON'
                    print 'trigger_settings parallel_options must have common_status_value_hex key'
                    return
                try:
                    self.trigger_parallel_port_off_value = int(parallel_options['common_status_value_hex'], 16)
                except ValueError as e:
                    print 'Invalid script JSON'
                    print 'trigger_settings parallel_options common_status_value_hex must be valid base-16 number'
                    print e
                    return
                # status port shouldn't have lower 3 bits set, nor exceed 8 bits
                if (self.trigger_parallel_port_off_value < 0 or
                        255 < self.trigger_parallel_port_off_value or
                        (self.trigger_parallel_port_off_value & 0x07) != 0):
                    print 'Invalid script JSON'
                    print 'trigger_settings parallel_options common_status_value_hex must be valid base-16 number between 0x08 and 0xF8 and with the bottom 3 bits zero'
                    return

                # required: ["active"] value for status port:
                if not parallel_options.has_key('trigger_status_value_hex'):
                    print 'Invalid script JSON'
                    print 'trigger_settings parallel_options must have trigger_status_value_hex key'
                    return
                try:
                    self.trigger_parallel_port_on_value = int(parallel_options['trigger_status_value_hex'], 16)
                except ValueError as e:
                    print 'Invalid script JSON'
                    print 'trigger_settings parallel_options trigger_status_value_hex must be valid base-16 number'
                    print e
                    return
                # status port shouldn't have lower 3 bits set, nor exceed 8 bits
                if (self.trigger_parallel_port_on_value < 0 or
                        255 < self.trigger_parallel_port_on_value or
                        (self.trigger_parallel_port_on_value & 0x07) != 0):
                    print 'Invalid script JSON'
                    print 'trigger_settings parallel_options trigger_status_value_hex must be valid base-16 number between 0x08 and 0xF8 and with the bottom 3 bits zero'
                    return
                # active value must be different from inactive value
                if self.trigger_parallel_port_off_value == self.trigger_parallel_port_on_value:
                    print 'Invalid script JSON'
                    print 'trigger_settings parallel_options trigger_status_value_hex and common_status_value_hex must have different values'
                    return

                self.prev_parallel_trigger_status_value = 0xFF  # an impossible value
            elif trigger_settings['mode'] == 'none':
                self.trigger_mode = None
            else:
                print 'trigger_settings mode of "' + trigger_settings[
                    'mode'] + '" should be one of keyboard, serial or none'
                return

        self.output_trigger_mode = None
        self.output_trigger_serial_port = None
        self.output_trigger_parallel_port_address = 0x0000
        self.output_trigger_parallel_port_off_value = 0x00
        self.output_trigger_parallel_port_on_frames = 3
        # used to hold output HIGH for # frames
        self.output_trigger_parallel_frame_countdown = 0

        self.output_trigger_parallel_send_byte_by_trigger = {}
        self.output_trigger_serial_send_strings_by_trigger = {}

        if self.script_json.has_key('output_trigger_settings'):
            output_settings = self.script_json['output_trigger_settings']
            if output_settings['mode'] == 'serial':
                self.output_trigger_mode = 'serial'
                # todo: implement serial output trigger
                # todo: handle using same serial port for input/output trigger
                serial_settings = output_settings['serial_options']

                serialport_options = dict(
                    port=serial_settings['port'],
                    timeout=0.0,
                    baudrate=19200)

                if serial_settings.has_key('bytesize'):
                    serialport_options['bytesize'] = int(serial_settings['bytesize'])
                if serial_settings.has_key('stopbits'):
                    serialport_options['stopbits'] = int(serial_settings['stopbits'])
                if serial_settings.has_key('parity'):
                    parity_options = dict(
                        even=serial.PARITY_EVEN,
                        mark=serial.PARITY_MARK,
                        names=serial.PARITY_NAMES,
                        none=serial.PARITY_NONE,
                        odd=serial.PARITY_ODD,
                        space=serial.PARITY_SPACE)
                    # convert parity option
                    if parity_options.has_key(serial_settings['parity']):
                        serialport_options['parity'] = parity_options[serial_settings['parity']]
                    else:
                        print ('serial_options parity value of "' + serial_settings['parity']
                               + '" was not one of the expected values: ' + json.dumps(parity_options.keys()))
                        return

                if self.trigger_serialport and serialport_options == self.trigger_serialport_options:
                    print 're-using incoming trigger serial port for output'
                    self.output_trigger_serial_port = self.trigger_serialport
                else:
                    try:
                        print 'opening serialport with options:', serialport_options
                        self.output_trigger_serial_port = serial.Serial(**serialport_options)
                    except serial.SerialException as e:
                        print 'could not open configured serial port for output trigger'
                        print e
                        print 'exiting.'
                        # exit
                        return

                # load list of triggers
                # if none supplied, error
                if self.output_trigger_mode != None and not output_settings.has_key(
                        'parallel_trigger_hex_values_by_event'):
                    print 'Invalid script JSON'
                    print 'output_trigger_settings must have serial_trigger_strings_by_event dictionary of strings/strings'
                    print 'please see the documentation for a sample file'
                    return

                if not isinstance(output_settings['serial_trigger_strings_by_event'], dict):
                    print 'Invalid script JSON'
                    print 'output_trigger_settings property serial_trigger_strings_by_event must be dictionary of string keys and string values'
                    print 'please see the documentation for a sample file'
                    return

                # validate trigger list entries are all known triggers
                for option, string_val in output_settings['serial_trigger_strings_by_event'].iteritems():
                    if not option in ALL_TRIGGERS:
                        print 'Invalid script JSON'
                        print 'output_trigger_settings trigger_list option of "%s" is not a known outbound trigger' % option
                        return
                    string_val = str(string_val)
                    self.output_trigger_serial_send_strings_by_trigger[option] = string_val

            elif output_settings['mode'] == 'parallel':
                self.output_trigger_mode = 'parallel'
                # required: parallel_options
                if not output_settings.has_key('parallel_options'):
                    print 'Invalid script JSON'
                    print 'parallel_options attribute is required for parallel mode output_trigger_settings'
                    return
                parallel_options = output_settings['parallel_options']

                # required: port address
                if not parallel_options.has_key('port_address_hex'):
                    print 'Invalid script JSON'
                    print 'output_trigger_settings parallel_options must have port_address_hex key'
                    return
                try:
                    self.output_trigger_parallel_port_address = int(parallel_options['port_address_hex'], 16)
                except ValueError as e:
                    print 'Invalid script JSON'
                    print 'output_trigger_settings parallel_options port_address_hex must be valid base-16 number'
                    print e
                    return

                # required: ["inactive"] value for data pins
                if not parallel_options.has_key('common_data_value_hex'):
                    print 'Invalid script JSON'
                    print 'output_trigger_settings parallel_options must have common_data_value_hex key'
                    return
                try:
                    self.output_trigger_parallel_port_off_value = int(parallel_options['common_data_value_hex'], 16)
                except ValueError as e:
                    print 'Invalid script JSON'
                    print 'output_trigger_settings parallel_options common_data_value_hex must be valid base-16 number'
                    print e
                    return

                # optional trigger_frames value
                if parallel_options.has_key('trigger_frames'):
                    try:
                        self.output_trigger_parallel_port_on_frames = int(parallel_options['trigger_frames'])
                    except ValueError as e:
                        print 'Invalid script JSON'
                        print 'output_trigger_settings parallel_options trigger_frames must be valid base-10 number'
                        print e
                        return

                # load list of triggers
                # if none supplied, error
                if self.output_trigger_mode != None and not output_settings.has_key(
                        'parallel_trigger_hex_values_by_event'):
                    print 'Invalid script JSON'
                    print 'output_trigger_settings must have parallel_trigger_hex_values_by_event dictionary of strings/strings'
                    print 'please see the documentation for a sample file'
                    return

                if not isinstance(output_settings['parallel_trigger_hex_values_by_event'], dict):
                    print 'Invalid script JSON'
                    print 'output_trigger_settings property parallel_trigger_hex_values_by_event must be dictionary of string keys and string values'
                    print 'please see the documentation for a sample file'
                    return

                # validate trigger list entries are all known triggers
                for option, byte_val_string in output_settings['parallel_trigger_hex_values_by_event'].iteritems():
                    if not option in ALL_TRIGGERS:
                        print 'Invalid script JSON'
                        print 'output_trigger_settings trigger_list option of "%s" is not a known outbound trigger' % option
                        return
                    # parse byte value
                    if byte_val_string.startswith('0x'):
                        pass
                    try:
                        byte_val = int(byte_val_string, 16)
                    except ValueError as e:
                        print e
                        print 'Invalid script JSON'
                        print '"%s" is not a valid base-16 integer' % byte_val_string
                        return
                    self.output_trigger_parallel_send_byte_by_trigger[option] = byte_val
            elif output_settings['mode'] == 'none':
                pass
            else:
                print 'output_trigger_settings mode of', output_settings['mode'], 'not recognized'
                return

        # number steps in original order:
        if self.script_json.has_key('group_shuffle_groups'):
            for i, s in enumerate(self.stepgroups):
                s['groupnumber'] = i + 1
        else:
            pass
        for i, s in enumerate(self.gamesteps):
            s['stepnumber'] = i + 1
        if self.script_json.has_key('group_shuffle_groups'):
            if not isinstance(self.script_json['group_shuffle_groups'], list):
                print
                'group_shuffle_groups must be list of lists of numbers'
                print
                'exiting.'

            for grp in self.script_json['group_shuffle_groups']:
                if not isinstance(grp, list):
                    print
                    'group_shuffle_groups must be list of lists of numbers'
                    print
                    'exiting.'
            # group_shuffle_groups specifies a list of "shuffle groups"
            # for groups in the json (defined using 'stepgroups')
            # each shuffle group is a list of group numbers, 1-based indexes
            # for original group position in the json
            # first we number the groups, then we iterate through each group of groups
            # and shuffle only groups with those original group numbers
            rnd = random.Random()
            stepgroups_old = self.stepgroups
            for g_numbers in self.script_json['group_shuffle_groups']:
                stepgroups_new = []
                g_steps = [s for s in self.stepgroups if s['groupnumber'] in g_numbers]
                if g_steps:
                    for s in stepgroups_old:
                        if s['groupnumber'] in g_numbers:
                            # choose random step to replace it from remaining g_steps
                            group_random = rnd.choice(g_steps)
                            g_steps.remove(group_random)
                            stepgroups_new.append(group_random)
                        else:
                            stepgroups_new.append(s)
                else:
                    stepgroups_new = stepgroups_old

                stepgroups_old = stepgroups_new

            self.stepgroups = stepgroups_old
            print 'Group order after shuffle(s):', ', '.join(str(s['groupnumber']) for s in self.stepgroups)

            if self.script_json.has_key('step_shuffle_groups'):
                if not isinstance(self.script_json['step_shuffle_groups'], list):
                    print
                    'step_shuffle_groups must be list of list of numbers'
                    print
                    'exiting.'

                for sg in self.script_json['step_shuffle_groups']:
                    if not isinstance(sg, list):
                        print
                        'step_shuffle_groups must be list of lists of numbers'
                        print
                        'exiting.'
                # step_shuffle_groups specifies a list of "shuffle groups"
                # for steps in the JSON (defined using 'steps')
                # each shuffle group is a list of step numbers, 1-based indexes for original step position
                # first we number the steps
                # then we iterate through each group and shuffle only steps with those original step numbers
                rnd = random.Random()
                # todo: verify self.script_json['step_randomization_groups'] is list of list of numbers
                gamesteps_old = self.gamesteps
                for g_numbers in script_json['step_shuffle_groups']:
                    gamesteps_new = []
                    g_steps = [s for s in self.gamesteps if s['stepnumber'] in g_numbers]
                    if g_steps:
                        for s in gamesteps_old:
                            if s['stepnumber'] in g_numbers:
                                # choose random step to replace it from remaining g_steps
                                step_random = rnd.choice(g_steps)
                                g_steps.remove(step_random)
                                gamesteps_new.append(step_random)
                            else:
                                gamesteps_new.append(s)
                    else:
                        gamesteps_new = gamesteps_old

                    gamesteps_old = gamesteps_new

                self.gamesteps = gamesteps_old
                print 'Step order after shuffle(s):', ', '.join(str(s['stepnumber']) for s in self.gamesteps)
            else:
                gamesteps_new = []
                for stepgroup in self.stepgroups:
                    for step in stepgroup['steps']:
                        gamesteps_new.append(step)
                self.gamesteps = gamesteps_new
                print 'Step order after shuffle(s):', ', '.join(str(s['stepnumber']) for s in self.gamesteps)
        else:
            print 'No shuffling. Step order:', ', '.join(str(s['stepnumber']) for s in self.gamesteps)
        # for i,s in enumerate(self.gamesteps):
        #     s['stepnumber'] = i+1
        # if self.script_json.has_key('step_shuffle_groups'):
        #     if not isinstance(self.script_json['step_shuffle_groups'], list):
        #         print 'step_shuffle_groups must be list of list of numbers'
        #         print 'exiting.'
        #         return
        #
        #     for sg in self.script_json['step_shuffle_groups']:
        #         if not isinstance(sg, list):
        #             print 'step_shuffle_groups must be list of lists of numbers'
        #             print 'exiting.'
        #             return
        #
        #     # step_shuffle_groups specifies a list of "shuffle groups"
        #     # each shuffle group is a list of step numbers, 1-based indexes for original step position
        #     # first we number the steps
        #     # then we iterate through each group and shuffle only steps with those original step numbers
        #     rnd = random.Random()
        #     # todo: verify self.script_json['step_randomization_groups'] is list of list of numbers
        #     gamesteps_old = self.gamesteps
        #     for g_numbers in self.script_json['step_shuffle_groups']:
        #         gamesteps_new = []
        #         g_steps = [s for s in self.gamesteps if s['stepnumber'] in g_numbers]
        #         if g_steps:
        #             for s in gamesteps_old:
        #                 if s['stepnumber'] in g_numbers:
        #                     # choose random step to replace it from remaining g_steps
        #                     step_random = rnd.choice(g_steps)
        #                     g_steps.remove(step_random)
        #                     gamesteps_new.append(step_random)
        #                 else:
        #                     gamesteps_new.append(s)
        #         else:
        #             gamesteps_new = gamesteps_old
        #
        #         gamesteps_old = gamesteps_new
        #
        #     self.gamesteps = gamesteps_old
        #     print 'Step order after shuffle(s):', ', '.join(str(s['stepnumber']) for s in self.gamesteps)

        if self.args.parallel_test_address:
            # try to parse parallel port address
            pport_debug_addr = int(self.args.parallel_test_address, 16)

            # ignore step list and replace with just parallel port test step
            self.gamesteps = [
                dict(action='parallel_port_test',
                     parallel_test_address=pport_debug_addr,
                     duration=None)]

        # validate steps and load levels:
        for i, step in enumerate(self.gamesteps):
            # duration must be not specified, none or float
            if step.has_key('duration'):
                if step['duration'] != None:
                    step['duration'] = float(step['duration'])
            else:
                step['duration'] = None

            if step.has_key('trigger_count'):
                if step['trigger_count'] != None:
                    step['trigger_count'] = int(step['trigger_count'])
            else:
                step['trigger_count'] = None

            # reaction_prompts
            if (step.has_key('reaction_prompts')
                    and step['reaction_prompts'] != None
                    and len(step['reaction_prompts']) > 0):
                for i, reaction_prompt_options in enumerate(step['reaction_prompts']):
                    # diameter should be number
                    if reaction_prompt_options.has_key('diameter'):
                        try:
                            reaction_prompt_options['diameter'] = float(reaction_prompt_options['diameter'])
                        except:
                            print "ERROR: reaction_prompts diameter value of %s should be a number" % repr(
                                reaction_prompt_options['diameter'])
                            return

                    # position_list should look like [ [0,10], [10,20] ]
                    if reaction_prompt_options.has_key('position_list'):
                        if not isinstance(reaction_prompt_options['position_list'], list):
                            print "ERROR: reaction_prompts position_list should be list of 2-element lists of numbers"
                            return
                        if len(reaction_prompt_options['position_list']) == 0:
                            print "ERROR: reaction_prompts position_list should be list of 2-element lists of numbers with at least one entry"
                            return
                        for pos in reaction_prompt_options['position_list']:
                            if not isinstance(pos, list) or len(pos) != 2:
                                print "ERROR: reaction_prompts position_list should be list of 2-element lists of numbers"
                                print 'found invalid entry:', repr(pos)
                                return
                            try:
                                left, top = pos
                                left += 5  # number-like check
                                top += 5
                            except:
                                print "ERROR: reaction_prompts position_list should be list of 2-element lists of numbers"
                                print 'found invalid entry:', repr(pos)
                                return

                    # image should be file in data directory. reported on load.
                    # sound should be file in data directory. reported on load.

                    # showtimes_millis should be list of numbers
                    if reaction_prompt_options.has_key('showtimes_millis'):
                        if not isinstance(reaction_prompt_options['showtimes_millis'], list):
                            print "ERROR: reaction_prompts showtimes_millis should be list of numbers"
                            return
                        for n in reaction_prompt_options['showtimes_millis']:
                            try:
                                n += 5  # number-like check
                            except:
                                print "ERROR: reaction_prompts showtimes_millis should be list of numbers"
                                return

                    # showtimes_trigger_counts should be list of numbers
                    if reaction_prompt_options.has_key('showtimes_trigger_counts'):
                        if not isinstance(reaction_prompt_options['showtimes_trigger_counts'], list):
                            print "ERROR: reaction_prompts showtimes_trigger_counts should be list of numbers"
                            return
                        for n in reaction_prompt_options['showtimes_trigger_counts']:
                            try:
                                n += 5  # number-like check
                            except:
                                print "ERROR: reaction_prompts showtimes_trigger_counts should be list of numbers"
                                return

                    # input_key should be string starting with K_. reported on load.

                    # timeout_millis should be number
                    if reaction_prompt_options.has_key('timeout_millis'):
                        if reaction_prompt_options['timeout_millis'] == 'never':
                            pass
                            # valid
                        else:
                            try:
                                d = float(reaction_prompt_options['timeout_millis'])
                            except:
                                print "ERROR: reaction_prompts timeout_millis value of %s should be a \"never\" or a number" % repr(
                                    reaction_prompt_options['timeout_millis'])
                                return

                    # score_pass should be number, or null/None
                    if reaction_prompt_options.has_key('score_pass'):
                        if reaction_prompt_options['score_pass'] == None:
                            pass
                            # valid
                        else:
                            try:
                                d = float(reaction_prompt_options['score_pass'])
                            except:
                                print "ERROR: reaction_prompts score_pass value of %s should be null or a number" % repr(
                                    reaction_prompt_options['score_pass'])
                                return

                    # score_fail should be number, or null/None
                    if reaction_prompt_options.has_key('score_fail'):
                        if reaction_prompt_options['score_fail'] == None:
                            pass
                            # valid
                        else:
                            try:
                                d = float(reaction_prompt_options['score_fail'])
                            except:
                                print "ERROR: reaction_prompts score_fail value of %s should be null or a number" % repr(
                                    reaction_prompt_options['score_fail'])
                                return

                    # score_miss should be number, or null/None
                    if reaction_prompt_options.has_key('score_miss'):
                        if reaction_prompt_options['score_miss'] == None:
                            pass
                            # valid
                        else:
                            try:
                                d = float(reaction_prompt_options['score_miss'])
                            except:
                                print "ERROR: reaction_prompts score_miss value of %s should be null or a number" % repr(
                                    reaction_prompt_options['score_miss'])
                                return

                    # fail_on_wrong_key should be either True or False
                    if reaction_prompt_options.has_key('fail_on_wrong_key'):
                        if reaction_prompt_options['fail_on_wrong_key'] == True or reaction_prompt_options[
                            'fail_on_wrong_key'] == False:
                            pass
                            # valid
                        else:
                            print "ERROR: reaction_prompts fail_on_wrong_key value should be true or false"
                            return

                    # pass_fail_sounds should be either True or False
                    if reaction_prompt_options.has_key('pass_fail_sounds'):
                        if reaction_prompt_options['pass_fail_sounds'] == True or reaction_prompt_options[
                            'pass_fail_sounds'] == False:
                            pass
                            # valid
                        else:
                            print "ERROR: reaction_prompts pass_fail_sounds value should be true or false"
                            return

            else:
                step['reaction_prompts'] = None

            if step['action'] == 'instructions':
                # nothing extra to validate
                pass
            elif step['action'] == 'text':
                # 'text' is required
                if not step.has_key('text'):
                    print ('ERROR: "text" step must have "text" attribute with string value.')
                    return
                # 'title' is optional
                if step.has_key('title'):
                    pass
                else:
                    step['title'] = ''
            elif step['action'] == 'survey':
                # 'prompt' is required
                if not step.has_key('prompt'):
                    print ('ERROR: "survey" step must have "prompt" attribute with string value.')
                    return
                # 'options' list is required
                if not step.has_key('options'):
                    print ('ERROR: "survey" step must have "options" attribute with an array of string values.')
                    return
            elif step['action'] == 'blackscreen':
                # duration and trigger_count are both optional, so nothing to validate
                pass
            elif step['action'] == 'game':
                # level json must be valid. Try loading levels
                if not step.has_key('levels'):
                    print ('ERROR: "game" action must have levels attribute pointing to ' +
                           'levels list json file.')
                    return

                step['levellist'] = self.load_levels(step)

                # other options
                if step.has_key('game_element_opacity'):
                    step['game_element_opacity'] = int(step['game_element_opacity'])
            elif step['action'] == 'game-adaptive':
                if not step.has_key('level_templates'):
                    print ('ERROR: "game" action must have level_templates attribute ' +
                           'with a list of level options or a string filename for a level ' +
                           'options json file, .')
                    return
                step['level_templates_list'] = self.load_level_templates(step)

                # simpler options options
                if step.has_key('start_level'):
                    step['start_level'] = float(step['start_level'])

                if step.has_key('level_completion_increment'):
                    step['level_completion_increment'] = float(step['level_completion_increment'])

                if step.has_key('level_death_decrement'):
                    step['level_death_decrement'] = float(step['level_death_decrement'])

                if step.has_key('continuous_asteroids_on_same_level'):
                    step['continuous_asteroids_on_same_level'] = bool(step['continuous_asteroids_on_same_level'])
                if step.has_key('adaptive_asteroid_size_locked_to_initial'):
                    step['adaptive_asteroid_size_locked_to_initial'] = bool(
                        step['adaptive_asteroid_size_locked_to_initial'])
                if step.has_key('show_advance_countdown'):
                    step['show_advance_countdown'] = bool(step['show_advance_countdown'])

                if step.has_key('game_element_opacity'):
                    step['game_element_opacity'] = int(step['game_element_opacity'])

                if step.has_key('multicolor_crystal_scoring'):
                    step['multicolor_crystal_scoring'] = bool(step['multicolor_crystal_scoring'])
                else:
                    step['multicolor_crystal_scoring'] = False

                if step.has_key('multicolor_crystal_numbers'):
                    # should be list of integers 1 <= n <= 5 for Crystal_1 through Crystal_5 graphics
                    if not isinstance(step['multicolor_crystal_numbers'], list):
                        print 'Error: game-adaptive multicolor_crystal_numbers must be a list of integers 1-5'
                        return
                    for n in step['multicolor_crystal_numbers']:
                        if not isinstance(n, int) or n < 1 or n > 5:
                            print 'Error: game-adaptive multicolor_crystal_numbers must be a list of integers 1-5'
                            print repr(n), 'is invalid'
                            return

                if step.has_key('multicolor_crystal_num_showing'):
                    step['multicolor_crystal_num_showing'] = int(step['multicolor_crystal_num_showing'])

                if step.has_key('multicolor_crystal_lifetime_ms'):
                    if (isinstance(step['multicolor_crystal_lifetime_ms'], float) or
                            isinstance(step['multicolor_crystal_lifetime_ms'], int)):
                        step['multicolor_crystal_lifetime_ms'] = int(step['multicolor_crystal_lifetime_ms'])
                    else:
                        step['multicolor_crystal_lifetime_ms'] = None

                if step.has_key('multicolor_crystal_negative_score_buzzer'):
                    step['multicolor_crystal_negative_score_buzzer'] = bool(
                        step['multicolor_crystal_negative_score_buzzer'])
                else:
                    step['multicolor_crystal_negative_score_buzzer'] = False

                if step.has_key('multicolor_crystal_score_table'):
                    if not isinstance(step['multicolor_crystal_score_table'], list):
                        print 'Error: game-adaptive multicolor_crystal_score_table must be a list of 5 lists of 6 score numbers'
                        return
                    # require 5 rows for the 5 different colors
                    if len(step['multicolor_crystal_score_table']) != 5:
                        print 'Error: game-adaptive multicolor_crystal_score_table must be a list of 5 lists of 6 score numbers'
                        print 'expected 5 rows, found', len(step['multicolor_crystal_score_table'])
                        return
                    for score_row in step['multicolor_crystal_score_table']:
                        if not isinstance(score_row, list):
                            print 'Error: game-adaptive multicolor_crystal_score_table must be a list of 5 lists of 6 score numbers'
                            print 'score row should be list of scores, but found non-list'
                            return
                        # require 6 rows for the 5 different colors the player collected previously, plus the score if they hadn't collected any previously
                        if len(score_row) != 6:
                            print 'Error: game-adaptive multicolor_crystal_score_table must be a list of 5 lists of 6 score numbers'
                            print 'score row should have 6 elements. One for each color, plus one for when no previous crystal was collected'
                            print 'expected 6 elements in inner list, found', len(score_row)
                            return
                        for score_cell in score_row:
                            if not isinstance(score_cell, int) and not isinstance(score_cell, float):
                                print 'Error: game-adaptive multicolor_crystal_score_table must be a list of 5 lists of 6 score numbers'
                                # expected int
                                print repr(score_cell), 'is an invalid score'
                                return
                    # convert scores into ints
                    step['multicolor_crystal_score_table'] = [[int(cell) for cell in row] for row in
                                                              step['multicolor_crystal_score_table']]

            elif step['action'] == 'parallel_port_test':
                # nothing else to validate
                pass

        resources.music_volume = self.args.music_volume
        resources.effects_volume = self.args.effects_volume

        if pygame.mixer:
            pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=256)

        displayflags = pygame.DOUBLEBUF
        if args.display_mode == 'fullscreen':
            displayflags |= pygame.FULLSCREEN
        else:
            # windowed
            if not self.args.parallel_test_address:
                displayflags |= pygame.NOFRAME
            if self.args.window_x != None and self.args.window_y != None:
                os.environ['SDL_VIDEO_WINDOW_POS'] = \
                    "%d,%d" % (self.args.window_x, self.args.window_y)
        screensize = (self.args.display_width, self.args.display_height)
        virtualdisplay.set_screensize(screensize)

        pygame.init()

        if not pygame.mixer.get_init():
            print 'Warning, could not initialize mixer. Game will have no sound.'

        if self.args.list_modes:
            print 'Available full screen display modes:'
            for mode in pygame.display.list_modes(0, pygame.DOUBLEBUF | pygame.FULLSCREEN):
                print '--display-mode fullscreen --display-width', mode[0], '--display-height', mode[1]
            # exit
            return

        self.screen = pygame.display.set_mode(screensize, displayflags)
        pygame.display.set_caption('Asteroid Impact')
        pygame.mouse.set_visible(0)
        # capture mouse
        pygame.event.set_grab(True)

        pygame.display.flip()

        # Init sequence of steps:
        self.stepindex = 0
        self.init_step()

        self.skipgame = False

    def init_step(self):
        "setup for next game mode step"
        self.step_millis = 0
        self.step_trigger_count = 0
        self.step_max_trigger_count = 2 ** 64
        self.step_max_millis = None
        step = self.gamesteps[self.stepindex]

        if step.has_key('duration') and step['duration'] != None:
            self.step_max_millis = int(1000 * step['duration'])

        if step.has_key('trigger_count') and step['trigger_count'] != None:
            self.step_max_trigger_count = int(step['trigger_count'])

        self.gamescreenstack = []
        if step['action'] == 'instructions':
            click_to_continue = True
            if step.has_key('duration') and step['duration'] != None:
                click_to_continue = False
            if step.has_key('trigger_count') and step['trigger_count'] != None:
                click_to_continue = False

            self.gamescreenstack.append(
                AsteroidImpactInstructionsScreen(
                    self.screen,
                    self.gamescreenstack,
                    click_to_continue=click_to_continue))
        elif step['action'] == 'instructions_alt':
            click_to_continue = True
            if step.has_key('duration') and step['duration'] != None:
                click_to_continue = False
            if step.has_key('trigger_count') and step['trigger_count'] != None:
                click_to_continue = False

            self.gamescreenstack.append(
                AsteroidImpactInstructionsScreenAlt(
                    self.screen,
                    self.gamescreenstack,
                    click_to_continue=click_to_continue))

        elif step['action'] == 'text':
            click_to_continue = True
            if step.has_key('duration') and step['duration'] != None:
                click_to_continue = False
            if step.has_key('trigger_count') and step['trigger_count'] != None:
                click_to_continue = False

            self.gamescreenstack.append(
                UserTextScreen(
                    self.screen,
                    self.gamescreenstack,
                    click_to_continue=click_to_continue,
                    text=step['text'],
                    title=step['title']))
        elif step['action'] == 'survey':
            click_to_continue = True
            if step.has_key('duration') and step['duration'] != None:
                click_to_continue = False
            if step.has_key('trigger_count') and step['trigger_count'] != None:
                click_to_continue = False

            self.gamescreenstack.append(
                SurveyQuestionScreen(
                    self.screen,
                    self.gamescreenstack,
                    prompt=step['prompt'],
                    survey_options=step['options'],
                    click_to_continue=click_to_continue))
        elif step['action'] == 'blackscreen':
            self.gamescreenstack.append(BlackScreen(self.screen, self.gamescreenstack))
        elif step['action'] == 'game':
            kwargs = {}
            if step.has_key('game_element_opacity'):
                kwargs['game_element_opacity'] = step['game_element_opacity']

            self.gamescreenstack.append(
                AsteroidImpactGameplayScreen(
                    self.screen,
                    self.gamescreenstack,
                    step['levellist'],
                    step['reaction_prompts'],
                    **kwargs))
        elif step['action'] == 'game-adaptive':
            kwargs = dict(game_globals=self.game_globals)
            if step.has_key('start_level'):
                kwargs['start_level'] = step['start_level']

            if step.has_key('level_completion_increment'):
                kwargs['level_completion_increment'] = step['level_completion_increment']

            if step.has_key('level_death_decrement'):
                kwargs['level_death_decrement'] = step['level_death_decrement']

            if step.has_key('continuous_asteroids_on_same_level'):
                kwargs['continuous_asteroids_on_same_level'] = step['continuous_asteroids_on_same_level']
            if step.has_key('adaptive_asteroid_size_locked_to_initial'):
                kwargs['adaptive_asteroid_size_locked_to_initial'] = step['adaptive_asteroid_size_locked_to_initial']
            if step.has_key('show_advance_countdown'):
                kwargs['show_advance_countdown'] = step['show_advance_countdown']

            if step.has_key('multicolor_crystal_scoring'):
                kwargs['multicolor_crystal_scoring'] = step['multicolor_crystal_scoring']
            else:
                kwargs['multicolor_crystal_scoring'] = False

            if step.has_key('multicolor_crystal_numbers'):
                kwargs['multicolor_crystal_numbers'] = step['multicolor_crystal_numbers']

            if step.has_key('multicolor_crystal_num_showing'):
                kwargs['multicolor_crystal_num_showing'] = step['multicolor_crystal_num_showing']

            if step.has_key('multicolor_crystal_lifetime_ms'):
                kwargs['multicolor_crystal_lifetime_ms'] = step['multicolor_crystal_lifetime_ms']

            if step.has_key('multicolor_crystal_score_table'):
                kwargs['multicolor_crystal_score_table'] = step['multicolor_crystal_score_table']

            if step.has_key('multicolor_crystal_negative_score_buzzer'):
                kwargs['multicolor_crystal_negative_score_buzzer'] = step['multicolor_crystal_negative_score_buzzer']

            if step.has_key('game_element_opacity'):
                kwargs['game_element_opacity'] = step['game_element_opacity']

            self.gamescreenstack.append(
                AsteroidImpactInfiniteGameplayScreen(
                    self.screen,
                    self.gamescreenstack,
                    step['level_templates_list'],
                    step['reaction_prompts'],
                    **kwargs))
        elif step['action'] == 'parallel_port_test':
            self.gamescreenstack.append(
                ParallelPortTestScreen(
                    self.screen,
                    self.gamescreenstack,
                    port_address=step['parallel_test_address']))
        else:
            raise ValueError('Unknown step action "%s"' % step['action'])

    def load_levels(self, step):
        "Load level details for game step from inline JSON or file"
        if isinstance(step['levels'], list):
            levellist = step['levels']
            dir = ''
        else:
            levelsabspath = os.path.abspath(step['levels'])
            dir, levellistfile = os.path.split(levelsabspath)

            "load levels from list of levels in JSON file"
            # load level list
            with open(path.join(dir, levellistfile)) as f:
                levellist = json.load(f)['levels']

        # load all levels in list
        levels = []
        # todo: allow level list of levels, not just level files?
        for levelfile in levellist:
            with open(path.join(dir, levelfile)) as f:
                level = json.load(f)
                level['level_name'] = levelfile
                levels.append(level)

        # find max # asteroids
        for level in levels:
            self.max_asteroid_count = max(
                self.max_asteroid_count, len(level['asteroids']))

        return levels

    def load_level_templates(self, step):
        "Load level templates for game-adaptive step from inline JSON or file"
        if isinstance(step['level_templates'], list):
            levellist = step['level_templates']
            dir = ''
        else:
            levelsabspath = os.path.abspath(step['level_templates'])
            dir, levellistfile = os.path.split(levelsabspath)

            "load levels from list of levels in JSON file"
            # load level list
            with open(path.join(dir, levellistfile)) as f:
                levellist = json.load(f)['levels']

        # load all levels in list
        levels = []
        for levelentry in levellist:
            if isinstance(levelentry, str):
                with open(path.join(dir, levelentry)) as f:
                    level = json.load(f)
                    level['level_name'] = levelentry
                    levels.append(level)
            else:
                levels.append(levelentry)

        # foo
        for level in levels:
            self.max_asteroid_count = max(
                self.max_asteroid_count, level['asteroid_count'])

        return levels

    def gameloop(self):
        # run the game frame/tick loop

        if self.skipgame:
            # exit
            return

        clock = pygame.time.Clock()

        if pygame.mixer and pygame.mixer.get_init():
            resources.load_music('through space.ogg')
            resources.unmute_music()
            pygame.mixer.music.play(-1)

        asteroidlogger = AsteroidLogger(self.args.log_filename, self.args.log_overwrite == 'true',
                                        self.max_asteroid_count)
        surveylogger = SurveyLogger(self.args.survey_log_filename, self.args.log_overwrite == 'true')
        reactionlogger = ReactionLogger(self.args.reaction_log_filename, self.args.log_overwrite == 'true')
        logrowdetails = {}

        self.total_millis = 0

        # cheesy 'framerate' display
        # mostly used to indicate if I'm getting 60fps or 30fps
        fps_display_enable = False
        fps_sprite = Target(diameter=8)
        fps_sprite.rect.top = 0
        fps_sprite_group = pygame.sprite.Group([fps_sprite])

        # trigger blink sprite
        trigger_blink_sprite = Target(diameter=32)
        trigger_blink_sprite.rect.top = 480 - 24
        trigger_blink_sprite.rect.left = 640 - 230

        if self.args.trigger_blink == 'true':
            trigger_blink_sprites = pygame.sprite.Group([trigger_blink_sprite])
        else:
            trigger_blink_sprites = pygame.sprite.Group([])

        if self.args.parallel_test_address:
            # try to parse parallel port address
            pport_debug_addr = int(self.args.parallel_test_address, 16)

            # ignore step list and just launch my new window
            # hack todo: replace step list with just this step
            self.gamescreenstack = []
            self.gamescreenstack.append(
                ParallelPortTestScreen(
                    self.screen,
                    self.gamescreenstack,
                    port_address=pport_debug_addr))
        else:
            pport_debug_addr = None

        # Main Loop
        first_update = True
        next_frame_outbound_triggers = []
        while 1:
            # more consistent, more cpu
            real_millis = clock.tick_busy_loop(60)
            trigger_received_this_tick = False
            # less repeatable, less cpu:
            # real_millis = clock.tick(60)

            if real_millis >= 25:
                # if we're not getting 60fps, then run update() extra times
                # find new frame durations that add-up to real_millis:
                frames = int(round(real_millis * .001 * 60))
                millis_list = [16] * frames
                millis_list[-1] = real_millis - 16 * (frames - 1)
            else:
                millis_list = (real_millis,)

            for millis in millis_list:
                # used to indicate we should quit game after finishing update logic for this frame
                quitgame = False
                self.total_millis += millis
                self.step_millis += millis

                frame_start_gamescreenstack = self.gamescreenstack[:]

                logrowdetails.clear()
                logrowdetails['subject_number'] = self.args.subject_number
                logrowdetails['subject_run'] = self.args.subject_run
                logrowdetails['step_number'] = self.gamesteps[self.stepindex]['stepnumber']
                logrowdetails['total_millis'] = self.total_millis
                logrowdetails['step_millis'] = self.step_millis
                logrowdetails['top_screen'] = self.gamescreenstack[-1].name

                frame_outbound_triggers = next_frame_outbound_triggers
                next_frame_outbound_triggers = []
                if first_update:
                    first_update = False
                    frame_outbound_triggers.append('step_begin')

                events = pygame.event.get()
                # Handle Keyboard triggers
                for event in events:
                    # check for keyboard trigger
                    if (self.trigger_mode == 'keyboard'
                            and self.trigger_key != None
                            and event.type == KEYDOWN
                            and event.key == self.trigger_key):
                        self.step_trigger_count += 1
                        trigger_received_this_tick = True

                # Check for serial trigger:
                if self.trigger_mode == 'serial' and self.trigger_serialport != None:
                    serial_input = self.trigger_serialport.read()
                    if serial_input:
                        for c in serial_input:
                            if ord(c) == self.trigger_serialport_byte_value:
                                self.step_trigger_count += 1
                                trigger_received_this_tick = True
                        # debug print:
                        print ">", repr(serial_input)
                        sys.stdout.flush()

                # check for parallel port trigger
                if self.trigger_mode == 'parallel':
                    current_parallel_trigger_status_value = self.get_parallel_trigger_status_value()
                    if (self.prev_parallel_trigger_status_value == self.trigger_parallel_port_off_value and
                            current_parallel_trigger_status_value == self.trigger_parallel_port_on_value):
                        self.step_trigger_count += 1
                        trigger_received_this_tick = True
                    self.prev_parallel_trigger_status_value = current_parallel_trigger_status_value

                logrowdetails['step_trigger_count'] = self.step_trigger_count

                try:
                    if len(self.gamescreenstack) > 0:
                        # update frontmost screen
                        self.gamescreenstack[-1].update_frontmost(millis, logrowdetails, frame_outbound_triggers,
                                                                  events, self.step_trigger_count, reactionlogger)
                        # update all screens in stack front to back
                        for screen in reversed(self.gamescreenstack):
                            screen.update_always(millis, logrowdetails, frame_outbound_triggers, events,
                                                 self.step_trigger_count, reactionlogger)
                except QuitGame as e:
                    print e
                    return

                # Handle Global Input Events
                for event in events:
                    if event.type == QUIT:
                        quitgame = True
                    elif (event.type == KEYDOWN
                          and event.key == K_q
                          and (event.mod & pygame.KMOD_META)):
                        print 'CMD+Q Pressed. Exiting'
                        quitgame = True
                    elif (event.type == KEYDOWN
                          and event.key == K_F4
                          and (event.mod & pygame.KMOD_ALT)):
                        print 'ALT+F4 Pressed. Exiting'
                        quitgame = True
                    elif (event.type == KEYDOWN
                          and event.key == K_c
                          and (event.mod & pygame.KMOD_ALT) != 0):
                        # toggle cursor capture and visibility:
                        current_grab = pygame.event.get_grab()
                        new_grab = not current_grab
                        pygame.event.set_grab(new_grab)
                        pygame.mouse.set_visible(not new_grab)
                    elif (event.type == KEYDOWN
                          and event.key == K_n
                          and (event.mod & pygame.KMOD_CTRL)):
                        print 'CTRL+n pressed. Advancing to next step'
                        self.gamescreenstack = []
                    else:
                        pass

                # Check if max duration on this step has expired
                step = self.gamesteps[self.stepindex]
                if self.step_max_millis != None and self.step_max_millis < self.step_millis:
                    # end this step:
                    self.gamescreenstack = []

                # Check if max trigger count on this step has expired
                if self.step_max_trigger_count != None and self.step_max_trigger_count <= self.step_trigger_count:
                    # end this step
                    self.gamescreenstack = []

                # call .after_close() on any now closed screens:
                for s in reversed(frame_start_gamescreenstack):
                    if quitgame or s not in self.gamescreenstack:
                        s.after_close(logrowdetails, reactionlogger, surveylogger)

                asteroidlogger.log(logrowdetails)

                self.update_outbound_triggers(frame_outbound_triggers)

                if len(self.gamescreenstack) == 0:
                    self.stepindex += 1
                    if self.stepindex >= len(self.gamesteps):
                        # all steps completed
                        quitgame = True
                    else:
                        # init step for next frame:
                        self.init_step()
                        next_frame_outbound_triggers.append('step_begin')

                # game quit is delayed to here so logging happens for final update
                if quitgame:
                    return

            # draw topmost opaque screen and everything above it
            topopaquescreenindex = -1
            for i in range(-1, -1 - len(self.gamescreenstack), -1):
                topopaquescreenindex = i
                if self.gamescreenstack[i].opaque:
                    break

            for screenindex in range(topopaquescreenindex, 0, 1):
                self.gamescreenstack[screenindex].draw()

            # cheesy 'no text' FPS display
            fps_sprite.rect.left = real_millis
            fps_sprite.rect.top = 16 * (int(round(real_millis * .001 * 60)) - 1)
            if fps_display_enable:
                fps_sprite_group.draw(self.screen)

            if trigger_received_this_tick:
                trigger_blink_sprites.draw(self.screen)

            pygame.display.flip()

    def get_parallel_trigger_status_value(self):
        # status byte is at base address + 1
        # mask off bottom 3 bits because they vary by parallel port card
        return parallelportwrapper.Inp32(self.trigger_parallel_port_address + 1) & 0xF8

    def update_outbound_triggers(self, frametriggerlist):
        print_triggers = False

        # see if there are any triggers to send
        send_trigger = False

        if self.output_trigger_mode == 'serial':
            serial_trigger_output_strings = []
            for t in frametriggerlist:
                if self.output_trigger_serial_send_strings_by_trigger.has_key(t):
                    serial_trigger_output_strings.append(self.output_trigger_serial_send_strings_by_trigger[t])
                    send_trigger = True
                    if print_triggers: print t
            if print_triggers and send_trigger: print

            if not send_trigger:
                return

            for s in serial_trigger_output_strings:
                self.output_trigger_serial_port.write(s)
            self.output_trigger_serial_port.flush()
        elif self.output_trigger_mode == 'parallel':
            parallel_trigger_bytes = []
            for t in frametriggerlist:
                if self.output_trigger_parallel_send_byte_by_trigger.has_key(t):
                    parallel_trigger_bytes.append(self.output_trigger_parallel_send_byte_by_trigger[t])
                    send_trigger = True
                    if print_triggers: print t
            if print_triggers and send_trigger: print

            if send_trigger:
                # combine multiple triggers from this frame by seeing which bits should be set/unset
                # compute 'on' value that has starts with self.output_trigger_parallel_port_off_value
                # then combines all changed bits from parallel_trigger_bytes corresponding to triggers this frame
                changed_bits = 0x00
                for b in parallel_trigger_bytes:
                    changed_bits = (changed_bits |
                                    # xor to find bits that this trigger changed from "off" byte value
                                    (b ^ self.output_trigger_parallel_port_off_value))
                active_value = self.output_trigger_parallel_port_off_value ^ changed_bits

                # start now
                self.output_trigger_parallel_frame_countdown = self.output_trigger_parallel_port_on_frames
                parallelportwrapper.Out32(
                    self.output_trigger_parallel_port_address,
                    active_value)
            else:
                # not a new trigger, but still need to handle switching to off when trigger frames end
                if self.output_trigger_parallel_frame_countdown > 0:
                    self.output_trigger_parallel_frame_countdown -= 1
                    if self.output_trigger_parallel_frame_countdown == 0:
                        # set parallel port output back to default value
                        parallelportwrapper.Out32(
                            self.output_trigger_parallel_port_address,
                            self.output_trigger_parallel_port_off_value)
        elif self.output_trigger_mode != None:
            raise QuitGame('output trigger mode of %s is not implemented' % self.output_trigger_mode)


def main():
    "parse console arguments and start game"
    args = parser.parse_args()

    game_step_manager = GameModeManager(args)
    game_step_manager.gameloop()


if __name__ == '__main__':
    main()
