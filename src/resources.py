# Asteroid Impact (c) Media Neuroscience Lab, Rene Weber
# Authored by Nick Winters
# 
# Asteroid Impact is licensed under a
# Creative Commons Attribution-ShareAlike 4.0 International License.
# 
# You should have received a copy of the license along with this
# work. If not, see <http://creativecommons.org/licenses/by-sa/4.0/>. 
"""
Resource-loading utilities for AsteroidImpact
"""


import os, sys, pygame
import pygame.ftfont

# Changing these only takes effect on newly loaded sounds
# so set volume before any sounds are loaded
music_volume = 1.0
effects_volume = 1.0

# scaledimage_cache[(some,key)] returns a ScaledImageCache
# see load_image()
scaledimage_cache = {}

sound_cache = {}

def resource_path(filename):
    """
    Return transformed resource path.
    
    For example, a standalone single-exe build would need to move the 'data' folder references somewhere else.
    """
    # The 'data' directory isn't in the same spot when pyinstaller creates a
    # standalone build packed exe:
    # (via http://irwinkwan.com/tag/pyinstaller/ )
    #if hasattr(sys, "_MEIPASS"):
    #	return os.path.join(sys._MEIPASS, filename)
    return os.path.join(filename)

#functions to create our resources
def load_font(name, size):
    'Load pygame font for specified filename, font size'
    fullname = resource_path(os.path.join('data', name))

    if pygame.ftfont:
        return pygame.ftfont.Font(fullname, size)

    class NoneFont:
        def __init__(self, filename, fontsize):
            self.fontsize = fontsize
        def render(self, text, antialias, color, background=None):
            'return no text on a new surface'
            s = pygame.Surface(self.size(text))
            s.fill(color)
            return s
        def size(self, text):
            'return size of text without font'
            return (self.fontsize*len(text)//4, self.fontsize)

    return NoneFont(fullname, size)

class ScaledImageCache(object):
    """
    Cache of image resources for different sizes.
    
    Make scaled images available more quickly by scaling them from a closer size to the 
    requested size than the image on disk. Cache the results for later.
    """
    def __init__(self, name, convert_alpha=False, colorkey=None):
        self.convert_alpha = convert_alpha
        self.colorkey = colorkey
        
        # load image resource without caching
        fullname = resource_path(os.path.join('data', name))
        try:
            fullsizeimage = pygame.image.load(fullname)
        except pygame.error as message:
            print('Cannot load image:', fullname)
            raise SystemExit(message)

        if self.convert_alpha:
            fullsizeimage = fullsizeimage.convert_alpha()
        elif self.colorkey is not None:
            if self.colorkey is -1:
                self.colorkey = fullsizeimage.get_at((0, 0))
            fullsizeimage.set_colorkey(colorkey, pygame.locals.RLEACCEL)
            fullsizeimage = fullsizeimage.convert()
        else:
            fullsizeimage = fullsizeimage.convert()

        # self.cache_by_log2_size[5] is image with size (2**5,2**5)
        self.cache_by_log2_size = []
        # self.cache_by_size[(48,48)] is image with size (48,48)
        self.cache_by_size = {}

        fullsizeimage_size = fullsizeimage.get_size()
        self.fullsizeimage_size = fullsizeimage_size
        maxsize = max(*self.fullsizeimage_size)
        # find log2(maxsize)
        while 2**len(self.cache_by_log2_size) < maxsize:
            self.cache_by_log2_size.append(None)

        for log2_size in range(len(self.cache_by_log2_size)):
            # todo: aspect preserve for non-square dimensions
            if fullsizeimage_size[0] < fullsizeimage_size[1]:
                width = 2**log2_size
                height = int(2**log2_size * fullsizeimage_size[1] / fullsizeimage_size[0])
                size = (width, height)
            else:
                height = 2**log2_size
                width = int(2**log2_size * fullsizeimage_size[0] / fullsizeimage_size[1])
                size = (width, height)
            image_scaled = pygame.transform.smoothscale(fullsizeimage, size)
            self.cache_by_log2_size[log2_size] = image_scaled
            self.cache_by_size[size] = image_scaled
        
    def get(self, size):
        """
        Return a cached previously scaled image

        or scale the image from the most suitable size if the size has not been requested before.
        """
        if size in self.cache_by_size:
            return self.cache_by_size[size]

        # find next larger log2 of diameter
        target_dia = 1
        log2_size = 0
        maxsize = max(*size)
        while log2_size < len(self.cache_by_log2_size) and target_dia < maxsize:
            target_dia *= 2
            log2_size += 1
        if log2_size >= len(self.cache_by_log2_size): log2_size = len(self.cache_by_log2_size)-1
        larger_img = self.cache_by_log2_size[log2_size]
        image_scaled = pygame.transform.smoothscale(larger_img, size)
        self.cache_by_size[size] = image_scaled

        return image_scaled

def load_image(name, size=None, convert_alpha=False, colorkey=None):
    """
    Load image, scaling to desired size if specified.
    
    Results are cached to make future loading of the same resource instant, but
    this means you shouldn't draw on returned surfaces.
    """

    if size == None:
        raise ValueError('please specify desired size')

    # Look up image in cache
    cache_key = (name, convert_alpha, colorkey)
    if cache_key in scaledimage_cache:
        return scaledimage_cache[cache_key].get(size)

    scaledimage_cache[cache_key] = ScaledImageCache(name, convert_alpha, colorkey)
    return scaledimage_cache[cache_key].get(size)

class NoneSound:
    '''Stub sound object that responds to same methods but plays no audio'''
    def __init__(self):
        self.volume = 1.0
    def play(self): pass
    def stop(self): pass
    def fadeout(self, duration): pass
    def get_length(self): return 1.0 #seconds
    def set_volume(self, volume): self.volume = volume
    def get_volume(self): return self.volume

class MixedSound(pygame.mixer.Sound):
    '''Sound object that reduces volume when self or other sounds in same group are played at simultaneously.'''
    def __init__(self, filename, mixing_group, default_volume):
        pygame.mixer.Sound.__init__(self, filename)
        self.filename = filename
        self.mixing_group = mixing_group
        self.default_volume = default_volume
        self.set_volume(self.default_volume)
    def play(self):
        # how many sounds in the current mixing group will be playing?
        # unfortunately s.get_num_channels() doesn't return only PLAYING channels

        playing_count_total = 0
        # find total playing count for mixing group:
        playing_count_by_filename = {}
        for i in range(pygame.mixer.get_num_channels()):
            channel = pygame.mixer.Channel(i)
            if channel.get_busy():
                s = channel.get_sound()
                if isinstance(s, MixedSound) and s.mixing_group == self.mixing_group:
                    if s.filename not in playing_count_by_filename:
                        playing_count_by_filename[s.filename] = (s, 1)
                    else:
                        playing_count_by_filename[s.filename] = (s, playing_count_by_filename[s.filename][1]+1)
                    playing_count_total += 1
        
        playing_count_total += 1 # me once I start playing
        # increment play count for me:
        if self.filename not in playing_count_by_filename:
            playing_count_by_filename[self.filename] = (self, 1)
        else:
            playing_count_by_filename[self.filename] = (self, playing_count_by_filename[self.filename][1]+1)

        # adjust volume of myself and others for number of times playing
        for filename,packed_val in playing_count_by_filename.items():
            s, playing_count_this = packed_val
            s.set_volume(s.default_volume * playing_count_this / playing_count_total)

        channel = pygame.mixer.Sound.play(self)
        # todo: register on sound ending to adjust volume again

def load_sound(name, mixing_group=None):
    """
    Load audio clip from file name.

    mixing_group is key for which group the sound should mix with. Mixed sounds in the same group
    reduce in volume based on how many are currently playing.
    """
    if not pygame.mixer or not pygame.mixer.get_init():
        return NoneSound()
    fullname = resource_path(os.path.join('data', name))
    try:
        key = (fullname, mixing_group)
        if key not in sound_cache:
            if not os.path.isfile(fullname):
                print('Cannot load sound:', fullname, 'file does not exist')
                raise SystemExit

            if not mixing_group:
                sound = pygame.mixer.Sound(fullname)
                sound.set_volume(effects_volume)
            else:
                sound = MixedSound(fullname, mixing_group, effects_volume)

            sound_cache[key] = sound
        return sound_cache[key]
    except pygame.error as message:
        print('Cannot load sound:', fullname)
        raise SystemExit(message)
    return sound

def load_music(name):
    """
    Load music file from file name.
    """
    if not pygame.mixer or not pygame.mixer.get_init():
        return
    fullname = resource_path(os.path.join('data', name))
    try:
        pygame.mixer.music.load(fullname)
    except pygame.error as message:
        print('Cannot load music:', fullname)
        raise SystemExit(message)

def mute_music():
    """Mute Music by setting volume to zero temporarily."""
    if not pygame.mixer or not pygame.mixer.get_init():
        return
    pygame.mixer.music.set_volume(0.0)

def unmute_music():
    """Restore music volume to configured music volume."""
    if not pygame.mixer or not pygame.mixer.get_init():
        return
    pygame.mixer.music.set_volume(music_volume)
