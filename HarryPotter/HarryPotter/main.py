"""
Ultimate Discord Bot - Fishing, Casino, Jobs, Music, AI Chat with Memory
A feature-rich Discord bot with beautiful UI, tutorials, and learning AI.
"""

import os
import asyncio
import random
import time
import aiosqlite
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import re

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.utils import get
from dotenv import load_dotenv

try:
    import openai
    from openai import OpenAI
except Exception:
    openai = None
    OpenAI = None

try:
    import yt_dlp
except Exception:
    yt_dlp = None

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

music_queues = {}

class MusicPlayer:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.queue = []
        self.current = None
        self.voice_client = None
        self.is_playing = False
        self.loop = False
    
    def add_to_queue(self, song: dict):
        self.queue.append(song)
    
    def get_next(self) -> Optional[dict]:
        if self.loop and self.current:
            return self.current
        if self.queue:
            self.current = self.queue.pop(0)
            return self.current
        self.current = None
        return None
    
    def clear_queue(self):
        self.queue.clear()
        self.current = None

def get_music_player(guild_id: int) -> MusicPlayer:
    if guild_id not in music_queues:
        music_queues[guild_id] = MusicPlayer(guild_id)
    return music_queues[guild_id]

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration', 0)
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader', 'Unknown')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        if not yt_dlp:
            return None
        ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

    @classmethod
    async def search(cls, query, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        if not yt_dlp:
            return None
        ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=not stream))
        if 'entries' in data and data['entries']:
            data = data['entries'][0]
        else:
            return None
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PREFIX = os.getenv("DEFAULT_PREFIX", "!")

if OPENAI_API_KEY and OpenAI:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    openai_client = None

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.reactions = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

DB_PATH = "bot_data.db"

RARITY_COLORS = {
    "common": 0x808080,
    "uncommon": 0x1EFF00,
    "rare": 0x0070DD,
    "epic": 0xA335EE,
    "legendary": 0xFF8000,
    "mythic": 0xFF00FF,
}

BIOMES = {
    "ocean": {"emoji": "🌊", "name": "Ocean", "fish_bonus": 1.0, "rare_bonus": 1.0, "min_level": 1, "description": "Calm waters, perfect for beginners"},
    "river": {"emoji": "🏞️", "name": "River", "fish_bonus": 0.95, "rare_bonus": 0.9, "min_level": 1, "description": "Flowing freshwater streams"},
    "lake": {"emoji": "🏕️", "name": "Lake", "fish_bonus": 0.9, "rare_bonus": 1.0, "min_level": 5, "description": "Peaceful lakeside fishing"},
    "tropical": {"emoji": "🏝️", "name": "Tropical", "fish_bonus": 1.1, "rare_bonus": 1.2, "min_level": 10, "description": "Exotic colorful fish await"},
    "swamp": {"emoji": "🐊", "name": "Swamp", "fish_bonus": 0.85, "rare_bonus": 1.3, "min_level": 15, "description": "Murky waters hide strange creatures"},
    "arctic": {"emoji": "🧊", "name": "Arctic", "fish_bonus": 0.8, "rare_bonus": 1.5, "min_level": 20, "description": "Icy depths with rare species"},
    "coral_reef": {"emoji": "🪸", "name": "Coral Reef", "fish_bonus": 1.15, "rare_bonus": 1.4, "min_level": 30, "description": "Vibrant underwater paradise"},
    "deep_sea": {"emoji": "🌑", "name": "Deep Sea", "fish_bonus": 0.75, "rare_bonus": 1.8, "min_level": 40, "description": "Abyssal zones with ancient creatures"},
    "volcanic": {"emoji": "🌋", "name": "Volcanic Vents", "fish_bonus": 0.7, "rare_bonus": 2.0, "min_level": 50, "description": "Extreme heat breeds extreme fish"},
    "bioluminescent": {"emoji": "💫", "name": "Bioluminescent Depths", "fish_bonus": 0.65, "rare_bonus": 2.2, "min_level": 60, "description": "Glowing creatures in eternal darkness"},
    "celestial_sea": {"emoji": "🌌", "name": "Celestial Sea", "fish_bonus": 0.6, "rare_bonus": 2.5, "min_level": 75, "description": "Where the sky meets the ocean"},
    "void_abyss": {"emoji": "🕳️", "name": "Void Abyss", "fish_bonus": 0.5, "rare_bonus": 3.0, "min_level": 100, "description": "The ultimate fishing challenge"},
}

FISH_DATA = {
    "common": [
        {"name": "Sardine", "emoji": "🐟", "xp": 10, "value": 5},
        {"name": "Anchovy", "emoji": "🐟", "xp": 12, "value": 6},
        {"name": "Herring", "emoji": "🐟", "xp": 15, "value": 8},
        {"name": "Mackerel", "emoji": "🐟", "xp": 18, "value": 10},
        {"name": "Sea Bass", "emoji": "🐟", "xp": 20, "value": 12},
        {"name": "Carp", "emoji": "🐟", "xp": 16, "value": 9},
        {"name": "Perch", "emoji": "🐟", "xp": 13, "value": 7},
        {"name": "Bluegill", "emoji": "🐟", "xp": 15, "value": 8},
        {"name": "Clownfish", "emoji": "🐠", "xp": 20, "value": 15},
    ],
    "uncommon": [
        {"name": "Bass", "emoji": "🐠", "xp": 35, "value": 25},
        {"name": "Trout", "emoji": "🐠", "xp": 40, "value": 30},
        {"name": "Salmon", "emoji": "🐠", "xp": 45, "value": 35},
        {"name": "Catfish", "emoji": "🐠", "xp": 50, "value": 40},
        {"name": "Pike", "emoji": "🐠", "xp": 55, "value": 45},
        {"name": "Red Snapper", "emoji": "🐠", "xp": 55, "value": 50},
        {"name": "Angelfish", "emoji": "🐠", "xp": 60, "value": 52},
    ],
    "rare": [
        {"name": "Tuna", "emoji": "🐡", "xp": 100, "value": 100},
        {"name": "Swordfish", "emoji": "🐡", "xp": 120, "value": 120},
        {"name": "Marlin", "emoji": "🐡", "xp": 140, "value": 140},
        {"name": "Barracuda", "emoji": "🐡", "xp": 160, "value": 160},
        {"name": "Sturgeon", "emoji": "🐟", "xp": 200, "value": 250},
    ],
    "epic": [
        {"name": "Shark", "emoji": "🦈", "xp": 300, "value": 350},
        {"name": "Manta Ray", "emoji": "🦈", "xp": 350, "value": 400},
        {"name": "Giant Squid", "emoji": "🦑", "xp": 400, "value": 450},
        {"name": "Orca", "emoji": "🐋", "xp": 450, "value": 500},
    ],
    "legendary": [
        {"name": "Golden Dragon", "emoji": "🐉", "xp": 800, "value": 1000},
        {"name": "Crystal Leviathan", "emoji": "💎", "xp": 900, "value": 1200},
        {"name": "Ancient Whale", "emoji": "🐋", "xp": 1000, "value": 1500},
    ],
    "mythic": [
        {"name": "The Void Entity", "emoji": "🕳️", "xp": 2000, "value": 5000},
        {"name": "Poseidon's Champion", "emoji": "👑", "xp": 2500, "value": 7500},
        {"name": "Primordial Ocean God", "emoji": "🌊", "xp": 3000, "value": 10000},
    ],
}

RARITY_WEIGHTS = {"common": 50, "uncommon": 30, "rare": 12, "epic": 5, "legendary": 2.5, "mythic": 0.5}

RODS = {
    1: {"name": "Wooden Rod", "emoji": "🪵", "catch_bonus": 1.0, "rare_bonus": 1.0, "cost": 0},
    2: {"name": "Bamboo Rod", "emoji": "🎋", "catch_bonus": 1.1, "rare_bonus": 1.1, "cost": 500},
    3: {"name": "Steel Rod", "emoji": "🔧", "catch_bonus": 1.2, "rare_bonus": 1.25, "cost": 2000},
    4: {"name": "Carbon Rod", "emoji": "⚫", "catch_bonus": 1.35, "rare_bonus": 1.5, "cost": 8000},
    5: {"name": "Titanium Rod", "emoji": "🔩", "catch_bonus": 1.5, "rare_bonus": 2.0, "cost": 25000},
    6: {"name": "Legendary Rod", "emoji": "✨", "catch_bonus": 2.0, "rare_bonus": 3.0, "cost": 100000},
}

BOATS = {
    1: {"name": "Raft", "emoji": "🪵", "cooldown_reduction": 0, "xp_bonus": 1.0, "cost": 0},
    2: {"name": "Canoe", "emoji": "🛶", "cooldown_reduction": 1, "xp_bonus": 1.1, "cost": 1000},
    3: {"name": "Sailboat", "emoji": "⛵", "cooldown_reduction": 2, "xp_bonus": 1.25, "cost": 5000},
    4: {"name": "Speedboat", "emoji": "🚤", "cooldown_reduction": 3, "xp_bonus": 1.5, "cost": 20000},
    5: {"name": "Yacht", "emoji": "🛥️", "cooldown_reduction": 4, "xp_bonus": 2.0, "cost": 75000},
    6: {"name": "Legendary Ship", "emoji": "🚢", "cooldown_reduction": 5, "xp_bonus": 3.0, "cost": 250000},
}

PETS = [
    {"id": 1, "name": "Lucky Cat", "emoji": "🐱", "bonus": "luck", "value": 0.05, "rarity": 5000},
    {"id": 2, "name": "Golden Turtle", "emoji": "🐢", "bonus": "xp", "value": 0.1, "rarity": 3000},
    {"id": 3, "name": "Mystic Dolphin", "emoji": "🐬", "bonus": "coins", "value": 0.15, "rarity": 4000},
    {"id": 4, "name": "Star Jellyfish", "emoji": "🪼", "bonus": "rare", "value": 0.08, "rarity": 6000},
    {"id": 5, "name": "Phoenix Fish", "emoji": "🔥", "bonus": "all", "value": 0.03, "rarity": 10000},
]

CHESTS = {
    "wooden": {"name": "Wooden Chest", "emoji": "📦", "drop_rate": 50, "color": 0x8B4513},
    "iron": {"name": "Iron Chest", "emoji": "🗃️", "drop_rate": 100, "color": 0xA8A8A8},
    "golden": {"name": "Golden Chest", "emoji": "📀", "drop_rate": 200, "color": 0xFFD700},
    "diamond": {"name": "Diamond Chest", "emoji": "💎", "drop_rate": 500, "color": 0x00FFFF},
    "mythic": {"name": "Mythic Chest", "emoji": "🌟", "drop_rate": 1000, "color": 0xFF00FF},
    "void": {"name": "Void Chest", "emoji": "🕳️", "drop_rate": 2500, "color": 0x4B0082},
}

CHEST_REWARDS = {
    "wooden": {"xp": (50, 150), "coins": (25, 75), "charm_chance": 0.05},
    "iron": {"xp": (150, 400), "coins": (75, 200), "charm_chance": 0.1},
    "golden": {"xp": (400, 1000), "coins": (200, 500), "charm_chance": 0.2},
    "diamond": {"xp": (1000, 3000), "coins": (500, 1500), "charm_chance": 0.35},
    "mythic": {"xp": (3000, 8000), "coins": (1500, 4000), "charm_chance": 0.5},
    "void": {"xp": (8000, 20000), "coins": (4000, 10000), "charm_chance": 0.75},
}

CHARMS = [
    {"id": 1, "name": "Lucky Charm", "emoji": "🍀", "bonus": "luck", "bonus_value": 0.05},
    {"id": 2, "name": "XP Charm", "emoji": "📈", "bonus": "xp", "bonus_value": 0.08},
    {"id": 3, "name": "Coin Charm", "emoji": "💰", "bonus": "coins", "bonus_value": 0.1},
    {"id": 4, "name": "Speed Charm", "emoji": "⚡", "bonus": "cooldown", "bonus_value": 0.1},
    {"id": 5, "name": "Rare Charm", "emoji": "💎", "bonus": "rare", "bonus_value": 0.12},
]

JOBS = {
    "fisher": {"name": "Fisherman", "emoji": "🎣", "base_pay": 50, "xp": 20, "cooldown": 60, "description": "Catch fish for the local market"},
    "diver": {"name": "Deep Sea Diver", "emoji": "🤿", "base_pay": 100, "xp": 40, "cooldown": 120, "min_level": 10, "description": "Explore underwater treasures"},
    "captain": {"name": "Ship Captain", "emoji": "🚢", "base_pay": 200, "xp": 80, "cooldown": 180, "min_level": 25, "description": "Navigate trade routes"},
    "marine_biologist": {"name": "Marine Biologist", "emoji": "🔬", "base_pay": 300, "xp": 120, "cooldown": 240, "min_level": 40, "description": "Study rare ocean life"},
    "treasure_hunter": {"name": "Treasure Hunter", "emoji": "🏴‍☠️", "base_pay": 500, "xp": 200, "cooldown": 300, "min_level": 60, "description": "Search for legendary treasures"},
    "oceanographer": {"name": "Oceanographer", "emoji": "🌊", "base_pay": 1000, "xp": 400, "cooldown": 600, "min_level": 80, "description": "Master of the seas"},
}

CASINO_GAMES = {
    "slots": {"name": "Slot Machine", "emoji": "🎰", "min_bet": 10, "max_bet": 10000},
    "blackjack": {"name": "Blackjack", "emoji": "🃏", "min_bet": 25, "max_bet": 25000},
    "roulette": {"name": "Roulette", "emoji": "🎡", "min_bet": 10, "max_bet": 50000},
    "dice": {"name": "Dice Roll", "emoji": "🎲", "min_bet": 5, "max_bet": 5000},
    "coinflip": {"name": "Coin Flip", "emoji": "🪙", "min_bet": 10, "max_bet": 100000},
}

TRIVIA_QUESTIONS = [
    {"question": "What is the capital of France?", "answer": "paris", "options": ["London", "Paris", "Berlin", "Madrid"]},
    {"question": "What planet is known as the Red Planet?", "answer": "mars", "options": ["Venus", "Mars", "Jupiter", "Saturn"]},
    {"question": "How many legs does a spider have?", "answer": "8", "options": ["6", "8", "10", "12"]},
    {"question": "What is the largest ocean?", "answer": "pacific", "options": ["Atlantic", "Indian", "Pacific", "Arctic"]},
    {"question": "What year did World War II end?", "answer": "1945", "options": ["1943", "1944", "1945", "1946"]},
    {"question": "What is the chemical symbol for gold?", "answer": "au", "options": ["Ag", "Au", "Fe", "Cu"]},
    {"question": "How many continents are there?", "answer": "7", "options": ["5", "6", "7", "8"]},
    {"question": "What is the largest mammal?", "answer": "blue whale", "options": ["Elephant", "Blue Whale", "Giraffe", "Hippo"]},
    {"question": "What is the hardest natural substance?", "answer": "diamond", "options": ["Gold", "Iron", "Diamond", "Platinum"]},
    {"question": "What is the speed of light in km/s?", "answer": "299792", "options": ["150000", "299792", "400000", "500000"]},
    {"question": "Who painted the Mona Lisa?", "answer": "leonardo da vinci", "options": ["Michelangelo", "Leonardo da Vinci", "Raphael", "Picasso"]},
    {"question": "What is the largest planet in our solar system?", "answer": "jupiter", "options": ["Saturn", "Jupiter", "Neptune", "Uranus"]},
    {"question": "How many bones are in the adult human body?", "answer": "206", "options": ["186", "206", "226", "256"]},
    {"question": "What is the smallest country in the world?", "answer": "vatican city", "options": ["Monaco", "Vatican City", "San Marino", "Liechtenstein"]},
    {"question": "What year was the first iPhone released?", "answer": "2007", "options": ["2005", "2006", "2007", "2008"]},
    {"question": "What is the tallest mountain in the world?", "answer": "everest", "options": ["K2", "Everest", "Kilimanjaro", "Denali"]},
    {"question": "How many strings does a standard guitar have?", "answer": "6", "options": ["4", "5", "6", "7"]},
    {"question": "What is the main ingredient in guacamole?", "answer": "avocado", "options": ["Tomato", "Avocado", "Onion", "Pepper"]},
    {"question": "What is the largest desert in the world?", "answer": "sahara", "options": ["Gobi", "Sahara", "Arabian", "Kalahari"]},
    {"question": "What is H2O commonly known as?", "answer": "water", "options": ["Oxygen", "Hydrogen", "Water", "Salt"]},
]

WORD_LIST = ["python", "discord", "fishing", "gaming", "adventure", "treasure", "ocean", "dragon", "crystal", "legend", "mystery", "quest", "wizard", "castle", "forest", "mountain", "river", "island", "sunset", "magic", "cosmic", "galaxy", "stellar", "nebula", "phoenix", "emerald", "sapphire", "diamond", "ancient", "mythical"]

EMOJI_GAMES = ["🎮", "🎲", "🎯", "🎪", "🎨", "🎭", "🎫", "🎬", "🎤", "🎧", "🎵", "🎷", "🎸", "🎹", "🎺", "🎻", "🥁", "🎰", "🎳", "🎱"]

RIDDLES = [
    {"riddle": "I have cities, but no houses. I have mountains, but no trees. I have water, but no fish. What am I?", "answer": "map"},
    {"riddle": "The more you take, the more you leave behind. What am I?", "answer": "footsteps"},
    {"riddle": "I speak without a mouth and hear without ears. I have no body, but I come alive with the wind. What am I?", "answer": "echo"},
    {"riddle": "What has keys but no locks, space but no room, and you can enter but can't go inside?", "answer": "keyboard"},
    {"riddle": "I'm tall when I'm young and short when I'm old. What am I?", "answer": "candle"},
    {"riddle": "What can travel around the world while staying in a corner?", "answer": "stamp"},
    {"riddle": "What has a head and a tail but no body?", "answer": "coin"},
    {"riddle": "What gets wetter the more it dries?", "answer": "towel"},
    {"riddle": "I have hands but can't clap. What am I?", "answer": "clock"},
    {"riddle": "What has many teeth but can't bite?", "answer": "comb"},
]

WOULD_YOU_RATHER = [
    ("be able to fly", "be invisible"),
    ("have unlimited money", "unlimited knowledge"),
    ("live without music", "live without movies"),
    ("be able to read minds", "predict the future"),
    ("live in the past", "live in the future"),
    ("have super strength", "super speed"),
    ("speak all languages", "talk to animals"),
    ("be famous", "be rich"),
    ("never eat pizza again", "never eat ice cream again"),
    ("have no phone", "have no computer"),
]

NEVER_HAVE_I_EVER = [
    "eaten an entire pizza by myself",
    "stayed awake for 24 hours straight",
    "pretended to be sick to skip something",
    "talked to myself in public",
    "laughed so hard I cried",
    "fallen asleep during a movie",
    "sent a text to the wrong person",
    "forgotten someone's name right after meeting them",
    "waved back at someone who wasn't waving at me",
    "walked into a glass door",
]

TRUTH_PROMPTS = [
    "What's your most embarrassing moment?",
    "What's your biggest fear?",
    "What's something you've never told anyone?",
    "What's your guilty pleasure?",
    "What's the most childish thing you still do?",
    "What's your biggest regret?",
    "What's the last lie you told?",
    "What's your secret talent?",
    "Who do you admire most?",
    "What's your dream job?",
]

DARE_PROMPTS = [
    "Send a message to your friend saying 'I love you'",
    "Post your most unflattering selfie",
    "Speak in an accent for the next 5 minutes",
    "Do 10 jumping jacks right now",
    "Text your crush 'hey'",
    "Change your profile picture to something silly",
    "Sing a song out loud",
    "Do your best impression of someone famous",
    "Talk in third person for 10 minutes",
    "Send a voice message of you singing",
]

MATH_OPERATIONS = ["+", "-", "*"]

puppy_training_sessions = {}

async def get_game_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT game_wins, game_losses, games_played FROM players WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row:
            return {"wins": row[0] or 0, "losses": row[1] or 0, "played": row[2] or 0}
        return {"wins": 0, "losses": 0, "played": 0}

SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣", "⭐"]
SLOT_PAYOUTS = {
    ("7️⃣", "7️⃣", "7️⃣"): 100,
    ("💎", "💎", "💎"): 50,
    ("⭐", "⭐", "⭐"): 25,
    ("🔔", "🔔", "🔔"): 15,
    ("🍇", "🍇", "🍇"): 10,
    ("🍊", "🍊", "🍊"): 8,
    ("🍋", "🍋", "🍋"): 5,
    ("🍒", "🍒", "🍒"): 3,
}

BASE_COOLDOWN = 10

CROPS = {
    "carrot": {"emoji": "🥕", "growth_time": 300, "xp": 20, "value": 50, "min_level": 1},
    "potato": {"emoji": "🥔", "growth_time": 600, "xp": 45, "value": 120, "min_level": 5},
    "corn": {"emoji": "🌽", "growth_time": 1200, "xp": 100, "value": 300, "min_level": 15},
    "strawberry": {"emoji": "🍓", "growth_time": 1800, "xp": 200, "value": 600, "min_level": 25},
    "melon": {"emoji": "🍉", "growth_time": 3600, "xp": 500, "value": 1500, "min_level": 40},
    "golden_wheat": {"emoji": "🌾", "growth_time": 7200, "xp": 1200, "value": 4000, "min_level": 60},
}

HUNTING_AREAS = {
    "forest": {"emoji": "🌲", "min_level": 1, "mobs": ["Rabbit", "Deer", "Wolf"], "relic_chance": 0.05},
    "desert": {"emoji": "🏜️", "min_level": 20, "mobs": ["Scorpion", "Snake", "Coyote"], "relic_chance": 0.1},
    "jungle": {"emoji": "🌴", "min_level": 40, "mobs": ["Panther", "Gorilla", "Tiger"], "relic_chance": 0.15},
    "mountains": {"emoji": "🏔️", "min_level": 60, "mobs": ["Eagle", "Bear", "Yeti"], "relic_chance": 0.2},
}

RELICS = {
    "ancient_eye": {"name": "Ancient Eye", "emoji": "👁️", "bonus": "crit", "value": 0.1},
    "dragon_scale": {"name": "Dragon Scale", "emoji": "🛡️", "bonus": "defense", "value": 0.15},
    "phoenix_feather": {"name": "Phoenix Feather", "emoji": "🪶", "bonus": "lifesteal", "value": 0.05},
}

DUNGEONS = {
    "shadow_crypt": {"name": "Shadow Crypt", "min_level": 10, "floors": 10, "emoji": "💀"},
    "crystal_cave": {"name": "Crystal Cave", "min_level": 30, "floors": 20, "emoji": "💎"},
    "void_tower": {"name": "Void Tower", "min_level": 70, "floors": 50, "emoji": "🌌"},
}

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                prestige INTEGER DEFAULT 0,
                coins INTEGER DEFAULT 100,
                rod_level INTEGER DEFAULT 1,
                boat_level INTEGER DEFAULT 1,
                total_fish INTEGER DEFAULT 0,
                current_biome TEXT DEFAULT 'ocean',
                last_fish_time REAL DEFAULT 0,
                last_work_time REAL DEFAULT 0,
                current_job TEXT DEFAULT NULL,
                casino_wins INTEGER DEFAULT 0,
                casino_losses INTEGER DEFAULT 0,
                total_earnings INTEGER DEFAULT 0,
                clan_id INTEGER DEFAULT NULL,
                game_wins INTEGER DEFAULT 0,
                game_losses INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                health INTEGER DEFAULT 100,
                max_health INTEGER DEFAULT 100,
                attack INTEGER DEFAULT 10,
                defense INTEGER DEFAULT 5,
                dungeon_rank TEXT DEFAULT 'Novice',
                relics TEXT DEFAULT '[]'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS farm (
                user_id INTEGER,
                plot_id INTEGER,
                crop_type TEXT,
                plant_time REAL,
                PRIMARY KEY (user_id, plot_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                traits TEXT DEFAULT '{}',
                interests TEXT DEFAULT '[]',
                learned_facts TEXT DEFAULT '[]',
                last_updated REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_sessions (
                user_id INTEGER PRIMARY KEY,
                type TEXT,
                prompt TEXT,
                history TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                user_id INTEGER,
                item_name TEXT,
                quantity INTEGER DEFAULT 0,
                item_type TEXT,
                PRIMARY KEY (user_id, item_name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fish_inventory (
                user_id INTEGER,
                fish_name TEXT,
                rarity TEXT,
                quantity INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, fish_name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                user_id INTEGER,
                pet_id INTEGER,
                PRIMARY KEY (user_id, pet_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chests (
                user_id INTEGER,
                chest_type TEXT,
                quantity INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, chest_type)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS charms (
                user_id INTEGER,
                charm_id INTEGER,
                quantity INTEGER DEFAULT 1,
                is_equipped INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, charm_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ai_memory (
                user_id INTEGER PRIMARY KEY,
                personality TEXT DEFAULT '',
                topics TEXT DEFAULT '[]',
                last_messages TEXT DEFAULT '[]',
                learned_facts TEXT DEFAULT '[]',
                interaction_count INTEGER DEFAULT 0,
                mood TEXT DEFAULT 'friendly',
                last_interaction REAL DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                welcome_channel_id INTEGER,
                modlog_channel_id INTEGER,
                music_channel_id INTEGER,
                auto_role_name TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS music_queue (
                guild_id INTEGER,
                position INTEGER,
                title TEXT,
                url TEXT,
                duration TEXT,
                requested_by INTEGER,
                PRIMARY KEY (guild_id, position)
            )
        """)
        await db.commit()

async def get_or_create_player(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row:
            cols = [desc[0] for desc in cur.description]
            return dict(zip(cols, row))
        await db.execute("INSERT INTO players (user_id) VALUES (?)", (user_id,))
        await db.commit()
        cur = await db.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))

async def update_player(user_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        sets = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        vals = list(kwargs.values()) + [user_id]
        await db.execute(f"UPDATE players SET {sets} WHERE user_id = ?", vals)
        await db.commit()

async def reset_player_data(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM players WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM fish_inventory WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM pets WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM chests WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM charms WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM ai_memory WHERE user_id = ?", (user_id,))
        await db.commit()
        return True

async def get_player_inventory(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT fish_name, rarity, quantity FROM fish_inventory WHERE user_id = ?", (user_id,))
        return await cur.fetchall()

async def add_fish_to_inventory(user_id: int, fish_name: str, rarity: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT quantity FROM fish_inventory WHERE user_id = ? AND fish_name = ?", (user_id, fish_name))
        row = await cur.fetchone()
        if row:
            await db.execute("UPDATE fish_inventory SET quantity = quantity + 1 WHERE user_id = ? AND fish_name = ?", (user_id, fish_name))
        else:
            await db.execute("INSERT INTO fish_inventory (user_id, fish_name, rarity, quantity) VALUES (?, ?, ?, 1)", (user_id, fish_name, rarity))
        await db.commit()

async def get_player_pets(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT pet_id FROM pets WHERE user_id = ?", (user_id,))
        return [row[0] for row in await cur.fetchall()]

async def add_pet_to_player(user_id: int, pet_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO pets (user_id, pet_id) VALUES (?, ?)", (user_id, pet_id))
        await db.commit()

async def get_player_chests(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT chest_type, quantity FROM chests WHERE user_id = ?", (user_id,))
        return {row[0]: row[1] for row in await cur.fetchall()}

async def add_chest_to_player(user_id: int, chest_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT quantity FROM chests WHERE user_id = ? AND chest_type = ?", (user_id, chest_type))
        row = await cur.fetchone()
        if row:
            await db.execute("UPDATE chests SET quantity = quantity + 1 WHERE user_id = ? AND chest_type = ?", (user_id, chest_type))
        else:
            await db.execute("INSERT INTO chests (user_id, chest_type, quantity) VALUES (?, ?, 1)", (user_id, chest_type))
        await db.commit()

async def remove_chest_from_player(user_id: int, chest_type: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT quantity FROM chests WHERE user_id = ? AND chest_type = ?", (user_id, chest_type))
        row = await cur.fetchone()
        if not row or row[0] < 1:
            return False
        if row[0] == 1:
            await db.execute("DELETE FROM chests WHERE user_id = ? AND chest_type = ?", (user_id, chest_type))
        else:
            await db.execute("UPDATE chests SET quantity = quantity - 1 WHERE user_id = ? AND chest_type = ?", (user_id, chest_type))
        await db.commit()
        return True

async def get_equipped_charms(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT charm_id FROM charms WHERE user_id = ? AND is_equipped = 1", (user_id,))
        return [row[0] for row in await cur.fetchall()]

async def get_ai_memory(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM ai_memory WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row:
            cols = [desc[0] for desc in cur.description]
            data = dict(zip(cols, row))
            data['topics'] = json.loads(data['topics']) if data['topics'] else []
            data['last_messages'] = json.loads(data['last_messages']) if data['last_messages'] else []
            data['learned_facts'] = json.loads(data['learned_facts']) if data['learned_facts'] else []
            return data
        await db.execute("INSERT INTO ai_memory (user_id) VALUES (?)", (user_id,))
        await db.commit()
        return {"user_id": user_id, "personality": "", "topics": [], "last_messages": [], "learned_facts": [], "interaction_count": 0, "mood": "friendly", "last_interaction": 0}

async def update_ai_memory(user_id: int, **kwargs):
    for key in ['topics', 'last_messages', 'learned_facts']:
        if key in kwargs and isinstance(kwargs[key], list):
            kwargs[key] = json.dumps(kwargs[key])
    async with aiosqlite.connect(DB_PATH) as db:
        sets = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        vals = list(kwargs.values()) + [user_id]
        await db.execute(f"UPDATE ai_memory SET {sets} WHERE user_id = ?", vals)
        await db.commit()

def calculate_level(xp: int) -> int:
    level = 1
    xp_required = 100
    while xp >= xp_required:
        level += 1
        xp_required += int(100 * (1.1 ** level))
    return level

def xp_to_next_level(xp: int, level: int) -> tuple:
    total_xp_needed = 0
    for lvl in range(1, level + 1):
        total_xp_needed += int(100 * (1.1 ** lvl))
    xp_into_level = xp - (total_xp_needed - int(100 * (1.1 ** level)))
    xp_for_next = int(100 * (1.1 ** (level + 1)))
    return max(0, xp_into_level), xp_for_next

def get_player_bonuses(player: dict, pets: list, charms: list) -> dict:
    bonuses = {"luck": 0, "xp": 0, "coins": 0, "cooldown": 0, "rare": 0, "all": 0}
    prestige_bonus = player.get("prestige", 0) * 0.05
    bonuses["all"] += prestige_bonus
    for pet_id in pets:
        pet = next((p for p in PETS if p["id"] == pet_id), None)
        if pet:
            bonuses[pet["bonus"]] += pet["value"]
    for charm_id in charms:
        charm = next((c for c in CHARMS if c["id"] == charm_id), None)
        if charm:
            bonuses[charm["bonus"]] += charm["bonus_value"]
    return bonuses

def roll_fish(biome: str, rod_level: int, bonuses: dict) -> tuple:
    biome_data = BIOMES.get(biome, BIOMES["ocean"])
    rod_data = RODS.get(rod_level, RODS[1])
    rare_mult = biome_data["rare_bonus"] * rod_data["rare_bonus"] * (1 + bonuses["rare"] + bonuses["all"])
    weights = []
    rarities = []
    for rarity, base_weight in RARITY_WEIGHTS.items():
        if rarity in ["legendary", "mythic"]:
            adjusted = base_weight * rare_mult
        elif rarity in ["epic", "rare"]:
            adjusted = base_weight * (1 + (rare_mult - 1) * 0.5)
        else:
            adjusted = base_weight
        weights.append(adjusted)
        rarities.append(rarity)
    total = sum(weights)
    weights = [w / total for w in weights]
    chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]
    fish_list = FISH_DATA[chosen_rarity]
    chosen_fish = random.choice(fish_list)
    return chosen_fish, chosen_rarity

def check_pet_drop(bonuses: dict) -> Optional[dict]:
    luck_bonus = 1 + bonuses["luck"] + bonuses["all"]
    for pet in PETS:
        chance = pet["rarity"] / luck_bonus
        if secrets.randbelow(max(1, int(chance))) == 0:
            return pet
    return None

def check_chest_drop(bonuses: dict) -> Optional[str]:
    luck_bonus = 1 + bonuses["luck"] + bonuses["all"]
    for chest_type, chest_data in CHESTS.items():
        chance = chest_data["drop_rate"] / luck_bonus
        if secrets.randbelow(max(1, int(chance))) == 0:
            return chest_type
    return None

class FarmView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your farm!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🌾 Wheat", style=discord.ButtonStyle.success, row=0)
    async def wheat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.plant_crop(interaction, "wheat")

    @discord.ui.button(label="🌽 Corn", style=discord.ButtonStyle.success, row=0)
    async def corn_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.plant_crop(interaction, "corn")

    @discord.ui.button(label="🥔 Potato", style=discord.ButtonStyle.success, row=0)
    async def potato_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.plant_crop(interaction, "potato")

    @discord.ui.button(label="🧺 Harvest All", style=discord.ButtonStyle.primary, row=1)
    async def harvest_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await harvest_crops(interaction)

    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.secondary, row=1)
    async def home_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_home(interaction)

    async def plant_crop(self, interaction: discord.Interaction, crop_type: str):
        user_id = interaction.user.id
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT COUNT(*) FROM farm WHERE user_id = ?", (user_id,))
            count = (await cur.fetchone())[0]
            if count >= 3:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Your farm is full! Harvest some crops first.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Your farm is full! Harvest some crops first.", ephemeral=True)
                return
            
            player = await get_or_create_player(user_id)
            crop_data = CROPS[crop_type]
            if player["coins"] < crop_data["cost"]:
                msg = f"❌ You need {crop_data['cost']} coins to plant {crop_type}!"
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
                return
            
            await update_player(user_id, coins=player["coins"] - crop_data["cost"])
            await db.execute("INSERT INTO farm (user_id, plot_id, crop_type, plant_time) VALUES (?, ?, ?, ?)",
                           (user_id, count + 1, crop_type, time.time()))
            await db.commit()
            
        msg = f"🌱 Planted **{crop_type.title()}**! (Cost: 🪙 {crop_data['cost']})"
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
        await show_farm_menu(interaction)

class HuntView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your hunt!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🌲 Woods", style=discord.ButtonStyle.success)
    async def woods_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()
        await do_hunting(interaction, area="whispering woods")

    @discord.ui.button(label="⛰️ Mountain", style=discord.ButtonStyle.success)
    async def mountain_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()
        await do_hunting(interaction, area="misty peaks")

    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.secondary)
    async def home_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_home(interaction)

class DungeonView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your dungeon!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🗡️ Fight", style=discord.ButtonStyle.danger)
    async def fight_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()
        await do_dungeon(interaction, dungeon="goblin den")

    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.secondary)
    async def home_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_home(interaction)

async def log_conversation(user_id: int, username: str, mode: str, role: str, content: str):
    """Log conversation to a text file organized by user and mode."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    folder_path = f"logs/conversations/{user_id}_{username}/{mode}"
    os.makedirs(folder_path, exist_ok=True)
    
    file_path = f"{folder_path}/{date_str}.txt"
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    log_entry = f"[{timestamp}] {role.upper()}: {content}\n"
    
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Logging error: {e}")

class AssistantView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="💬 Just Chatting", style=discord.ButtonStyle.primary)
    async def chat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_mode(interaction, "chatting")

    @discord.ui.button(label="🗣️ Venting", style=discord.ButtonStyle.success)
    async def vent_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_mode(interaction, "venting")

    @discord.ui.button(label="🎭 Roleplay", style=discord.ButtonStyle.secondary)
    async def rp_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_mode(interaction, "roleplay")

    @discord.ui.button(label="🛑 Deactivate", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE ai_sessions SET is_active = 0 WHERE user_id = ? AND type = 'assistant'", (self.user_id,))
            await db.commit()
        await interaction.response.send_message("👋 Personal assistant deactivated. I'll stop checking in on you.", ephemeral=True)

    async def set_mode(self, interaction: discord.Interaction, mode: str):
        prompt = "You are Harry, a friendly and caring personal assistant. "
        if mode == "venting":
            prompt += "The user wants to vent. Be an empathetic listener, offer support, and don't judge. Focus on emotional support."
        elif mode == "roleplay":
            prompt += "The user wants to roleplay. Engage in an immersive roleplay scenario with them. Stay in character and follow their lead."
        else:
            prompt += "The user wants to just chat. Be engaging, friendly, and helpful. Keep the conversation light and fun."
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE ai_sessions SET prompt = ?, is_active = 2, type = ? WHERE user_id = ?", 
                           (prompt, f"assistant_{mode}", self.user_id))
            await db.commit()
        
        await interaction.response.send_message(f"✅ Mode set to **{mode.title()}**! I'm now listening and will reply to every message. Type `menu` anytime to change modes.", ephemeral=True)

@bot.tree.command(name="assistant", description="Activate your personal assistant for DM check-ins")
async def assistant_command(interaction: discord.Interaction):
    user_id = interaction.user.id
    await save_ai_session(user_id, 'assistant', 'You are a helpful personal assistant checking in on the user.', [], is_active=1)
    
    embed = discord.Embed(
        title="🤖 Personal Assistant Activated",
        description="I'm now your personal assistant! I'll check in on you periodically via DM to see how you're doing and help with anything you need.",
        color=0x7289DA
    )
    embed.add_field(name="How it works", value="I'll send you a message every few hours to check in. You can talk to me just like the regular AI chat!")
    
    try:
        view = AssistantView(user_id)
        await interaction.user.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Activated! Check your DMs.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I can't send you DMs! Please enable DMs from server members.", ephemeral=True)

async def check_in_task():
    await bot.wait_until_ready()
    while not bot.is_closed():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id FROM ai_sessions WHERE type = 'assistant' AND is_active = 1") as cursor:
                async for row in cursor:
                    user_id = row[0]
                    try:
                        user = await bot.fetch_user(user_id)
                        api_key = os.getenv("OPENROUTER_API_KEY")
                        if api_key:
                            from openai import OpenAI
                            client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
                            messages = [
                                {"role": "system", "content": "You are Harry, a friendly and caring personal assistant. Send a short, warm check-in message to the user asking how they are or if they need help with anything."},
                            ]
                            completion = client.chat.completions.create(
                                model="google/gemini-2.0-flash-001",
                                messages=messages,
                            )
                            check_in_msg = completion.choices[0].message.content
                        else:
                            check_in_msg = "Hello! Just checking in to see how you're doing today. Is there anything I can help you with? 🌟"
                        
                        await user.send(check_in_msg)
                    except Exception as e:
                        print(f"Check-in error for {user_id}: {e}")
        
        await asyncio.sleep(3600 * 4) # Check in every 4 hours

async def show_farm_menu(interaction: discord.Interaction):
    user_id = interaction.user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM farm WHERE user_id = ?", (user_id,))
        plots = await cur.fetchall()
        
        embed = discord.Embed(title="🚜 Your Farm", color=discord.Color.green())
        if not plots:
            embed.description = "You don't have anything planted yet! Use `/plant` to start farming."
        else:
            farm_text = ""
            now = time.time()
            for plot_id, crop_type, plant_time in [(p[1], p[2], p[3]) for p in plots]:
                crop = CROPS.get(crop_type)
                elapsed = now - plant_time
                remaining = max(0, crop["growth_time"] - elapsed)
                status = "✅ Ready!" if remaining == 0 else f"⏳ {int(remaining/60)}m left"
                farm_text += f"Plot {plot_id}: {crop['emoji']} **{crop_type.title()}** ({status})\n"
            embed.add_field(name="Current Crops", value=farm_text)
        
        view = FarmView(user_id)
        try:
            await interaction.response.send_message(embed=embed, view=view)
        except:
            await interaction.edit_original_response(embed=embed, view=view)

async def harvest_crops(interaction: discord.Interaction):
    user_id = interaction.user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT plot_id, crop_type, plant_time FROM farm WHERE user_id = ?", (user_id,))
        plots = await cur.fetchall()
        
        if not plots:
            await interaction.followup.send("You don't have anything planted!", ephemeral=True)
            return
            
        now = time.time()
        harvested = []
        total_coins = 0
        total_xp = 0
        
        for plot_id, crop_type, plant_time in plots:
            crop = CROPS[crop_type]
            if now - plant_time >= crop["growth_time"]:
                harvested.append(plot_id)
                total_coins += crop["value"]
                total_xp += crop["xp"]
        
        if not harvested:
            await interaction.followup.send("Nothing is ready to harvest yet!", ephemeral=True)
            return
        
        for plot_id in harvested:
            await db.execute("DELETE FROM farm WHERE user_id = ? AND plot_id = ?", (user_id, plot_id))
        
        await db.execute("UPDATE players SET coins = coins + ?, xp = xp + ? WHERE user_id = ?", (total_coins, total_xp, user_id))
        await db.commit()
        
    await interaction.followup.send(f"🚜 **Harvested {len(harvested)} crops!**\n💰 Earned **{total_coins}** coins\n⭐ Gained **{total_xp}** XP")
    await show_farm_menu(interaction)

async def do_hunting(interaction: discord.Interaction, area: str):
    area = area.lower()
    if area not in HUNTING_AREAS:
        if interaction.response.is_done():
            await interaction.followup.send("Invalid area!", ephemeral=True)
        else:
            await interaction.response.send_message("Invalid area!", ephemeral=True)
        return
        
    user_id = interaction.user.id
    player_data = await get_or_create_player(user_id)
    area_data = HUNTING_AREAS[area]
    
    if player_data["level"] < area_data["min_level"]:
        msg = f"You need level {area_data['min_level']} to hunt here!"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return
        
    mob = random.choice(area_data["mobs"])
    success = random.random() > 0.3
    
    if success:
        coins = random.randint(50, 200) * (HUNTING_AREAS[area]["min_level"] / 5 + 1)
        xp = random.randint(30, 100)
        relic_msg = ""
        if random.random() < area_data["relic_chance"]:
            relic_id = random.choice(list(RELICS.keys()))
            relic = RELICS[relic_id]
            relic_msg = f"\n✨ **FOUND A RELIC:** {relic['emoji']} {relic['name']}!"
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE players SET coins = coins + ?, xp = xp + ? WHERE user_id = ?", (int(coins), xp, user_id))
            await db.commit()
            
        embed = discord.Embed(title="🏹 Hunting Success", description=f"You hunted a **{mob}** in the {area}!\n💰 +{int(coins)} coins\n⭐ +{xp} XP{relic_msg}", color=discord.Color.green())
    else:
        embed = discord.Embed(title="🏹 Hunting Failed", description=f"You tracked a **{mob}**, but it escaped...", color=discord.Color.red())
    
    view = HuntView(user_id)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=embed, view=view)

async def do_dungeon(interaction: discord.Interaction, dungeon: str):
    user_id = interaction.user.id
    player_data = await get_or_create_player(user_id)
    d_data = DUNGEONS.get(dungeon)
    
    if player_data["level"] < d_data["min_level"]:
        msg = f"You need level {d_data['min_level']} to enter!"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return
        
    floor = random.randint(1, d_data["floors"])
    enemy_hp = floor * 20
    win = player_data["attack"] * random.uniform(0.8, 1.2) > (enemy_hp / 10)
    
    if win:
        coins = floor * 100
        xp = floor * 50
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE players SET coins = coins + ?, xp = xp + ? WHERE user_id = ?", (coins, xp, user_id))
            await db.commit()
        embed = discord.Embed(title=f"🏰 {d_data['emoji']} Dungeon Clear", description=f"**Floor {floor} Cleared!**\n💰 +{coins} coins\n⭐ +{xp} XP", color=discord.Color.green())
    else:
        embed = discord.Embed(title=f"🏰 {d_data['emoji']} Dungeon Failed", description=f"**Floor {floor} Failed.**\n💀 You retreated.", color=discord.Color.red())
    
    view = DungeonView(user_id)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=embed, view=view)

class HomeView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🎣 Fishing", style=discord.ButtonStyle.success, row=0)
    async def fishing_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_fishing_menu(interaction)

    @discord.ui.button(label="🎰 Casino", style=discord.ButtonStyle.danger, row=0)
    async def casino_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_casino_menu(interaction)

    @discord.ui.button(label="💼 Jobs", style=discord.ButtonStyle.primary, row=0)
    async def jobs_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_jobs_menu(interaction)

    @discord.ui.button(label="🎵 Music", style=discord.ButtonStyle.secondary, row=0)
    async def music_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_music_menu(interaction)

    @discord.ui.button(label="👤 Profile", style=discord.ButtonStyle.secondary, row=1)
    async def profile_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_profile(interaction)

    @discord.ui.button(label="📚 Tutorials", style=discord.ButtonStyle.secondary, row=1)
    async def tutorials_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_tutorials_menu(interaction)

    @discord.ui.button(label="🛒 Shop", style=discord.ButtonStyle.success, row=1)
    async def shop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_shop_menu(interaction)

    @discord.ui.button(label="🔧 Upgrades", style=discord.ButtonStyle.success, row=1)
    async def upgrades_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_upgrades_menu(interaction)

    @discord.ui.button(label="🚜 Farm", style=discord.ButtonStyle.primary, row=2)
    async def farm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()
        await show_farm_menu(interaction)

    @discord.ui.button(label="🏹 Hunt", style=discord.ButtonStyle.primary, row=2)
    async def hunt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()
        await do_hunting(interaction, area="whispering woods")

    @discord.ui.button(label="🏰 Dungeon", style=discord.ButtonStyle.primary, row=2)
    async def dungeon_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()
        await do_dungeon(interaction, dungeon="goblin den")

    @discord.ui.button(label="⚙️ Settings", style=discord.ButtonStyle.secondary, row=2)
    async def settings_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_settings_menu(interaction)

class TutorialView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🎣 Fishing Tutorial", style=discord.ButtonStyle.primary, row=0)
    async def fishing_tut(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🎣 Fishing Tutorial", color=0x00AAFF)
        embed.add_field(name="Getting Started", value="Use `/fish` to start fishing! Cast your line and catch fish to earn XP and coins.", inline=False)
        embed.add_field(name="Biomes", value="Unlock new biomes as you level up! Each biome has unique fish and better rare chances.", inline=False)
        embed.add_field(name="Equipment", value="Buy better rods and boats from the shop to catch better fish and reduce cooldowns.", inline=False)
        embed.add_field(name="Pets & Chests", value="Rare pets can drop while fishing! Chests contain XP, coins, and charms.", inline=False)
        embed.add_field(name="Prestige", value="At level 50+, you can prestige to reset progress but gain permanent bonuses!", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🎰 Casino Tutorial", style=discord.ButtonStyle.danger, row=0)
    async def casino_tut(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🎰 Casino Tutorial", color=0xFF0000)
        embed.add_field(name="Games Available", value="**Slots** - Spin for matching symbols\n**Blackjack** - Get 21!\n**Roulette** - Bet on numbers or colors\n**Dice** - Roll higher than the dealer\n**Coinflip** - 50/50 chance!", inline=False)
        embed.add_field(name="Betting", value="Each game has min/max bet limits. Don't bet more than you can afford to lose!", inline=False)
        embed.add_field(name="Payouts", value="Slots: Up to 100x on jackpot!\nBlackjack: 2.5x on blackjack, 2x on win\nRoulette: 35x on numbers, 2x on colors", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="💼 Jobs Tutorial", style=discord.ButtonStyle.success, row=0)
    async def jobs_tut(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="💼 Jobs Tutorial", color=0x00FF00)
        embed.add_field(name="Working", value="Use `/work` to do your job and earn coins and XP! Higher level jobs pay more.", inline=False)
        embed.add_field(name="Job Types", value="🎣 Fisherman (Lv.1)\n🤿 Deep Sea Diver (Lv.10)\n🚢 Ship Captain (Lv.25)\n🔬 Marine Biologist (Lv.40)\n🏴‍☠️ Treasure Hunter (Lv.60)\n🌊 Oceanographer (Lv.80)", inline=False)
        embed.add_field(name="Cooldowns", value="Each job has a cooldown. Better jobs have longer cooldowns but pay more!", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🎵 Music Tutorial", style=discord.ButtonStyle.primary, row=1)
    async def music_tut(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🎵 Music Tutorial", color=0x1DB954)
        embed.add_field(name="Playing Music", value="Use `/play <link or search>` to play music from YouTube or Spotify!", inline=False)
        embed.add_field(name="Supported Links", value="YouTube videos & playlists\nSpotify tracks & playlists\nOr just search by name!", inline=False)
        embed.add_field(name="Controls", value="`/pause` - Pause playback\n`/resume` - Resume playback\n`/skip` - Skip current song\n`/queue` - View queue\n`/stop` - Stop and clear queue", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🤖 AI Chat Tutorial", style=discord.ButtonStyle.secondary, row=1)
    async def ai_tut(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🤖 AI Chat Tutorial", color=0x7289DA)
        embed.add_field(name="Talking to the Bot", value="Use `/talk <message>` to chat with the AI! It remembers your conversations.", inline=False)
        embed.add_field(name="Learning", value="The AI learns from your conversations! Share facts, preferences, and it will remember.", inline=False)
        embed.add_field(name="Personality", value="The more you chat, the more the AI adapts to your style and interests.", inline=False)
        embed.add_field(name="Memory", value="The AI remembers topics you've discussed, facts you've shared, and your mood!", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🔙 Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_home(interaction)

class FishingView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your fishing session!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🎣 Cast Line", style=discord.ButtonStyle.success, custom_id="fish_cast")
    async def cast_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await do_fishing(interaction)

    @discord.ui.button(label="🌍 Change Biome", style=discord.ButtonStyle.primary, custom_id="fish_biome")
    async def biome_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_biome_select(interaction)

    @discord.ui.button(label="📦 Inventory", style=discord.ButtonStyle.secondary, custom_id="fish_inv")
    async def inv_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        inv = await get_player_inventory(self.user_id)
        if not inv:
            await interaction.response.send_message("Your inventory is empty! Go catch some fish! 🎣", ephemeral=True)
            return
        embed = discord.Embed(title="📦 Your Fish Collection", color=0x00AAFF)
        rarity_groups = {}
        for fish_name, rarity, qty in inv:
            if rarity not in rarity_groups:
                rarity_groups[rarity] = []
            rarity_groups[rarity].append(f"{fish_name} x{qty}")
        for rarity in ["mythic", "legendary", "epic", "rare", "uncommon", "common"]:
            if rarity in rarity_groups:
                embed.add_field(name=f"{rarity.title()} Fish", value="\n".join(rarity_groups[rarity]), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📊 Stats", style=discord.ButtonStyle.secondary, custom_id="fish_stats")
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await get_or_create_player(self.user_id)
        pets = await get_player_pets(self.user_id)
        rod = RODS[player["rod_level"]]
        boat = BOATS[player["boat_level"]]
        xp_into, xp_needed = xp_to_next_level(player["xp"], player["level"])
        progress = min(10, int((xp_into / max(1, xp_needed)) * 10))
        bar = "█" * progress + "░" * (10 - progress)
        embed = discord.Embed(title=f"📊 {interaction.user.display_name}'s Stats", color=0x00FF88)
        embed.add_field(name="Level", value=f"**{player['level']}** (P{player['prestige']})", inline=True)
        embed.add_field(name="XP", value=f"{xp_into:,}/{xp_needed:,}\n[{bar}]", inline=True)
        embed.add_field(name="Coins", value=f"🪙 {player['coins']:,}", inline=True)
        embed.add_field(name="Total Fish", value=f"🐟 {player['total_fish']:,}", inline=True)
        embed.add_field(name="Rod", value=f"{rod['emoji']} {rod['name']}", inline=True)
        embed.add_field(name="Boat", value=f"{boat['emoji']} {boat['name']}", inline=True)
        if pets:
            pet_names = [f"{PETS[pid-1]['emoji']} {PETS[pid-1]['name']}" for pid in pets if pid <= len(PETS)]
            embed.add_field(name="Pets", value="\n".join(pet_names) or "None", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.secondary, custom_id="fish_home")
    async def home_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_home(interaction)

class CasinoView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your casino!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🎰 Slots", style=discord.ButtonStyle.danger, row=0)
    async def slots_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_slots_game(interaction)

    @discord.ui.button(label="🃏 Blackjack", style=discord.ButtonStyle.primary, row=0)
    async def blackjack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_blackjack_game(interaction)

    @discord.ui.button(label="🎡 Roulette", style=discord.ButtonStyle.success, row=0)
    async def roulette_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_roulette_game(interaction)

    @discord.ui.button(label="🎲 Dice", style=discord.ButtonStyle.secondary, row=1)
    async def dice_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_dice_game(interaction)

    @discord.ui.button(label="🪙 Coinflip", style=discord.ButtonStyle.primary, row=1)
    async def coinflip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_coinflip_game(interaction)

    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.secondary, row=1)
    async def home_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_home(interaction)

class JobsView(discord.ui.View):
    def __init__(self, user_id: int, player_level: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.player_level = player_level

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🎣 Fisherman", style=discord.ButtonStyle.success, row=0)
    async def fisher_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await do_work(interaction, "fisher")

    @discord.ui.button(label="🤿 Diver", style=discord.ButtonStyle.primary, row=0)
    async def diver_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player_level < 10:
            await interaction.response.send_message("You need to be level 10 to work as a Diver!", ephemeral=True)
        else:
            await do_work(interaction, "diver")

    @discord.ui.button(label="🚢 Captain", style=discord.ButtonStyle.primary, row=0)
    async def captain_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player_level < 25:
            await interaction.response.send_message("You need to be level 25 to work as a Captain!", ephemeral=True)
        else:
            await do_work(interaction, "captain")

    @discord.ui.button(label="🔬 Biologist", style=discord.ButtonStyle.secondary, row=1)
    async def biologist_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player_level < 40:
            await interaction.response.send_message("You need to be level 40 to work as a Marine Biologist!", ephemeral=True)
        else:
            await do_work(interaction, "marine_biologist")

    @discord.ui.button(label="🏴‍☠️ Treasure Hunter", style=discord.ButtonStyle.danger, row=1)
    async def treasure_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.player_level < 60:
            await interaction.response.send_message("You need to be level 60 to work as a Treasure Hunter!", ephemeral=True)
        else:
            await do_work(interaction, "treasure_hunter")

    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.secondary, row=1)
    async def home_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_home(interaction)

class ShopView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your shop!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🎣 Upgrade Rod", style=discord.ButtonStyle.success, row=0)
    async def rod_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await get_or_create_player(self.user_id)
        current = player["rod_level"]
        if current >= len(RODS):
            await interaction.response.send_message("You have the best rod already! 🎣", ephemeral=True)
            return
        next_rod = RODS[current + 1]
        if player["coins"] < next_rod["cost"]:
            await interaction.response.send_message(f"You need 🪙 **{next_rod['cost']:,}** coins! (You have {player['coins']:,})", ephemeral=True)
            return
        await update_player(self.user_id, rod_level=current + 1, coins=player["coins"] - next_rod["cost"])
        await interaction.response.send_message(f"Upgraded to {next_rod['emoji']} **{next_rod['name']}**!", ephemeral=True)

    @discord.ui.button(label="🚤 Upgrade Boat", style=discord.ButtonStyle.primary, row=0)
    async def boat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await get_or_create_player(self.user_id)
        current = player["boat_level"]
        if current >= len(BOATS):
            await interaction.response.send_message("You have the best boat already! 🚢", ephemeral=True)
            return
        next_boat = BOATS[current + 1]
        if player["coins"] < next_boat["cost"]:
            await interaction.response.send_message(f"You need 🪙 **{next_boat['cost']:,}** coins! (You have {player['coins']:,})", ephemeral=True)
            return
        await update_player(self.user_id, boat_level=current + 1, coins=player["coins"] - next_boat["cost"])
        await interaction.response.send_message(f"Upgraded to {next_boat['emoji']} **{next_boat['name']}**!", ephemeral=True)

    @discord.ui.button(label="⭐ Prestige", style=discord.ButtonStyle.danger, row=0)
    async def prestige_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = await get_or_create_player(self.user_id)
        if player["level"] < 50:
            await interaction.response.send_message(f"You need to be level **50** to prestige! (Currently level {player['level']})", ephemeral=True)
            return
        new_prestige = player["prestige"] + 1
        await update_player(self.user_id, xp=0, level=1, prestige=new_prestige, rod_level=1, boat_level=1, coins=0)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM fish_inventory WHERE user_id = ?", (self.user_id,))
            await db.commit()
        await interaction.response.send_message(f"🌟 **PRESTIGE {new_prestige}!** You've been reset but gained permanent +{new_prestige * 5}% to all bonuses!", ephemeral=True)

    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.secondary, row=1)
    async def home_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_home(interaction)

class SettingsView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🗑️ Reset All Data", style=discord.ButtonStyle.danger, row=0)
    async def reset_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="⚠️ Reset All Data?", description="This will delete ALL your progress:\n- Level, XP, Coins\n- Fish inventory\n- Pets, Chests, Charms\n- AI memory\n\n**This cannot be undone!**", color=0xFF0000)
        view = ConfirmResetView(self.user_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🧠 Clear AI Memory", style=discord.ButtonStyle.secondary, row=0)
    async def clear_ai_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await update_ai_memory(self.user_id, personality="", topics=[], last_messages=[], learned_facts=[], interaction_count=0, mood="friendly")
        await interaction.response.send_message("AI memory cleared! The bot has forgotten everything about you.", ephemeral=True)

    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.secondary, row=1)
    async def home_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_home(interaction)

class ConfirmResetView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Yes, Reset Everything", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await reset_player_data(self.user_id)
        await interaction.response.send_message("All your data has been reset. Start fresh with `/home`!", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Reset cancelled.", ephemeral=True)
        self.stop()

class BiomeSelect(discord.ui.Select):
    def __init__(self, player_level: int):
        options = []
        for biome_key, biome_data in list(BIOMES.items())[:25]:
            locked = player_level < biome_data["min_level"]
            if locked:
                label = f"{biome_data['name']} (Lv.{biome_data['min_level']}+)"
                description = f"Unlock at level {biome_data['min_level']}"
            else:
                label = biome_data["name"]
                description = biome_data["description"][:50]
            options.append(discord.SelectOption(label=label, value=biome_key, emoji=biome_data["emoji"], description=description))
        super().__init__(placeholder="Select a biome...", options=options, min_values=1, max_values=1)
        self.player_level = player_level

    async def callback(self, interaction: discord.Interaction):
        biome_key = self.values[0]
        biome_data = BIOMES[biome_key]
        if self.player_level < biome_data["min_level"]:
            await interaction.response.send_message(f"You need level **{biome_data['min_level']}** for {biome_data['emoji']} {biome_data['name']}!", ephemeral=True)
            return
        await update_player(interaction.user.id, current_biome=biome_key)
        await interaction.response.send_message(f"Changed biome to {biome_data['emoji']} **{biome_data['name']}**!", ephemeral=True)

class BiomeSelectView(discord.ui.View):
    def __init__(self, user_id: int, player_level: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.add_item(BiomeSelect(player_level))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

async def show_home(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    xp_into, xp_needed = xp_to_next_level(player["xp"], player["level"])
    progress = min(20, int((xp_into / max(1, xp_needed)) * 20))
    bar = "█" * progress + "░" * (20 - progress)
    
    embed = discord.Embed(title=f"🏠 Welcome, {interaction.user.display_name}!", description="Your personal adventure hub! Choose an activity below.", color=0x00AAFF)
    embed.add_field(name="📊 Your Stats", value=f"**Level:** {player['level']} (P{player['prestige']})\n**XP:** [{bar}] {xp_into:,}/{xp_needed:,}\n**Coins:** 🪙 {player['coins']:,}\n**Fish Caught:** 🐟 {player['total_fish']:,}", inline=False)
    embed.add_field(name="🎮 Activities", value="🎣 **Fishing** - Catch fish, earn XP!\n🎰 **Casino** - Test your luck!\n💼 **Jobs** - Work for coins!\n🎵 **Music** - Play tunes!", inline=False)
    embed.add_field(name="📌 Quick Tips", value="• Use `/fish` to start fishing\n• Use `/talk` to chat with AI\n• Use `/play` for music", inline=False)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Use the buttons below to navigate!")
    
    view = HomeView(interaction.user.id)
    try:
        await interaction.response.send_message(embed=embed, view=view)
    except:
        await interaction.followup.send(embed=embed, view=view)

async def show_fishing_menu(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    biome = BIOMES[player["current_biome"]]
    rod = RODS[player["rod_level"]]
    boat = BOATS[player["boat_level"]]
    
    embed = discord.Embed(title="🎣 Fishing Adventure", description=f"Currently at: {biome['emoji']} **{biome['name']}**\n\n*{biome['description']}*", color=0x00AAFF)
    embed.add_field(name="Equipment", value=f"{rod['emoji']} **{rod['name']}**\n{boat['emoji']} **{boat['name']}**", inline=True)
    embed.add_field(name="Biome Bonuses", value=f"Fish: {int(biome['fish_bonus']*100)}%\nRare: {int(biome['rare_bonus']*100)}%", inline=True)
    embed.add_field(name="Stats", value=f"Level: **{player['level']}** | Fish: **{player['total_fish']:,}**", inline=True)
    embed.set_footer(text="Cast your line to catch fish and earn rewards!")
    
    view = FishingView(interaction.user.id)
    try:
        await interaction.response.send_message(embed=embed, view=view)
    except:
        await interaction.followup.send(embed=embed, view=view)

async def show_biome_select(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    view = BiomeSelectView(interaction.user.id, player["level"])
    await interaction.response.send_message("Select a biome:", view=view, ephemeral=True)

async def do_fishing(interaction: discord.Interaction):
    user_id = interaction.user.id
    player = await get_or_create_player(user_id)
    pets = await get_player_pets(user_id)
    equipped_charms = await get_equipped_charms(user_id)
    bonuses = get_player_bonuses(player, pets, equipped_charms)
    
    boat = BOATS[player["boat_level"]]
    cooldown = BASE_COOLDOWN - boat["cooldown_reduction"] - int(BASE_COOLDOWN * bonuses["cooldown"])
    cooldown = max(3, cooldown)
    time_since = time.time() - player["last_fish_time"]
    if time_since < cooldown:
        remaining = int(cooldown - time_since)
        await interaction.followup.send(f"Wait **{remaining}s** before fishing again!", ephemeral=True)
        return
    
    biome = player["current_biome"]
    rod = RODS[player["rod_level"]]
    fish, rarity = roll_fish(biome, player["rod_level"], bonuses)
    
    xp_mult = boat["xp_bonus"] * (1 + bonuses["xp"] + bonuses["all"])
    xp_gain = int(fish["xp"] * xp_mult)
    coin_mult = 1 + bonuses["coins"] + bonuses["all"]
    coin_gain = int(fish["value"] * coin_mult)
    
    new_xp = player["xp"] + xp_gain
    new_level = calculate_level(new_xp)
    level_up = new_level > player["level"]
    
    await update_player(user_id, xp=new_xp, level=new_level, coins=player["coins"] + coin_gain, total_fish=player["total_fish"] + 1, last_fish_time=time.time())
    await add_fish_to_inventory(user_id, fish["name"], rarity)
    
    pet_found = check_pet_drop(bonuses)
    new_pet = False
    if pet_found:
        owned_pets = await get_player_pets(user_id)
        if pet_found["id"] not in owned_pets:
            await add_pet_to_player(user_id, pet_found["id"])
            new_pet = True
    
    chest_found = check_chest_drop(bonuses)
    if chest_found:
        await add_chest_to_player(user_id, chest_found)
    
    biome_data = BIOMES[biome]
    embed = discord.Embed(title=f"{biome_data['emoji']} Fishing in {biome_data['name']}", color=RARITY_COLORS.get(rarity, 0x808080))
    embed.add_field(name="🎣 Caught!", value=f"{fish['emoji']} **{fish['name']}**\n*{rarity.title()}*", inline=True)
    embed.add_field(name="💰 Rewards", value=f"+{xp_gain:,} XP\n+{coin_gain:,} coins", inline=True)
    embed.add_field(name="🔧 Equipment", value=f"{rod['emoji']} {rod['name']}\n{boat['emoji']} {boat['name']}", inline=True)
    
    if level_up:
        unlocked_biomes = [b for b_key, b in BIOMES.items() if b["min_level"] == new_level]
        level_text = f"🎉 Level **{new_level}**!"
        if unlocked_biomes:
            level_text += f"\n{unlocked_biomes[0]['emoji']} Unlocked: **{unlocked_biomes[0]['name']}**!"
        embed.add_field(name="⬆️ LEVEL UP!", value=level_text, inline=False)
    
    if new_pet and pet_found:
        embed.add_field(name="🐾 PET FOUND!", value=f"{pet_found['emoji']} **{pet_found['name']}** joined you!", inline=False)
    
    if chest_found:
        chest_data = CHESTS[chest_found]
        embed.add_field(name="📦 CHEST FOUND!", value=f"{chest_data['emoji']} **{chest_data['name']}**\nUse `/openchest` to open!", inline=False)
    
    embed.set_footer(text=f"Total fish: {player['total_fish'] + 1:,} | Level {new_level}")
    view = FishingView(user_id)
    await interaction.followup.send(embed=embed, view=view)

async def show_casino_menu(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    
    embed = discord.Embed(title="🎰 Welcome to the Casino!", description="Test your luck and win big! Choose a game below.", color=0xFF0000)
    embed.add_field(name="💰 Your Balance", value=f"🪙 **{player['coins']:,}** coins", inline=False)
    embed.add_field(name="📊 Casino Stats", value=f"Wins: **{player['casino_wins']}**\nLosses: **{player['casino_losses']}**", inline=True)
    embed.add_field(name="🎮 Games", value="🎰 **Slots** - Match symbols!\n🃏 **Blackjack** - Beat the dealer!\n🎡 **Roulette** - Pick your number!\n🎲 **Dice** - Roll high!\n🪙 **Coinflip** - 50/50!", inline=False)
    embed.set_footer(text="Remember: Only bet what you can afford to lose!")
    
    view = CasinoView(interaction.user.id)
    try:
        await interaction.response.send_message(embed=embed, view=view)
    except:
        await interaction.followup.send(embed=embed, view=view)

async def show_slots_game(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    min_bet = CASINO_GAMES["slots"]["min_bet"]
    
    if player["coins"] < min_bet:
        await interaction.response.send_message(f"You need at least {min_bet} coins to play slots!", ephemeral=True)
        return
    
    bet = min(100, player["coins"])
    reels = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
    
    winnings = 0
    result = tuple(reels)
    if result in SLOT_PAYOUTS:
        winnings = bet * SLOT_PAYOUTS[result]
    elif reels[0] == reels[1] or reels[1] == reels[2]:
        winnings = bet
    
    new_coins = player["coins"] - bet + winnings
    if winnings > 0:
        await update_player(interaction.user.id, coins=new_coins, casino_wins=player["casino_wins"] + 1)
        result_text = f"🎉 **YOU WON {winnings:,} coins!**"
        color = 0x00FF00
    else:
        await update_player(interaction.user.id, coins=new_coins, casino_losses=player["casino_losses"] + 1)
        result_text = f"💔 You lost {bet} coins..."
        color = 0xFF0000
    
    embed = discord.Embed(title="🎰 Slot Machine", color=color)
    embed.add_field(name="Reels", value=f"╔═══════════╗\n║  {reels[0]}  {reels[1]}  {reels[2]}  ║\n╚═══════════╝", inline=False)
    embed.add_field(name="Result", value=result_text, inline=False)
    embed.add_field(name="Balance", value=f"🪙 {new_coins:,} coins", inline=True)
    embed.add_field(name="Bet", value=f"🪙 {bet} coins", inline=True)
    
    await interaction.response.send_message(embed=embed)

async def show_blackjack_game(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    min_bet = CASINO_GAMES["blackjack"]["min_bet"]
    
    if player["coins"] < min_bet:
        await interaction.response.send_message(f"You need at least {min_bet} coins to play blackjack!", ephemeral=True)
        return
    
    bet = min(100, player["coins"])
    cards = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
    suits = ["♠️", "♥️", "♦️", "♣️"]
    
    player_cards = [random.choice(cards), random.choice(cards)]
    dealer_cards = [random.choice(cards), random.choice(cards)]
    
    def calc_hand(hand):
        total = 0
        aces = 0
        for card in hand:
            if card in ["J", "Q", "K"]:
                total += 10
            elif card == "A":
                total += 11
                aces += 1
            else:
                total += int(card)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total
    
    player_total = calc_hand(player_cards)
    dealer_total = calc_hand(dealer_cards)
    
    while dealer_total < 17:
        dealer_cards.append(random.choice(cards))
        dealer_total = calc_hand(dealer_cards)
    
    if player_total == 21:
        winnings = int(bet * 2.5)
        result = "🎉 BLACKJACK! You win!"
        color = 0x00FF00
    elif player_total > 21:
        winnings = 0
        result = "💔 Bust! You lose."
        color = 0xFF0000
    elif dealer_total > 21:
        winnings = bet * 2
        result = "🎉 Dealer busts! You win!"
        color = 0x00FF00
    elif player_total > dealer_total:
        winnings = bet * 2
        result = "🎉 You win!"
        color = 0x00FF00
    elif dealer_total > player_total:
        winnings = 0
        result = "💔 Dealer wins."
        color = 0xFF0000
    else:
        winnings = bet
        result = "🤝 Push! Bet returned."
        color = 0xFFFF00
    
    new_coins = player["coins"] - bet + winnings
    if winnings > bet:
        await update_player(interaction.user.id, coins=new_coins, casino_wins=player["casino_wins"] + 1)
    elif winnings < bet:
        await update_player(interaction.user.id, coins=new_coins, casino_losses=player["casino_losses"] + 1)
    else:
        await update_player(interaction.user.id, coins=new_coins)
    
    embed = discord.Embed(title="🃏 Blackjack", color=color)
    embed.add_field(name="Your Hand", value=f"{' '.join(player_cards)} = **{player_total}**", inline=True)
    embed.add_field(name="Dealer's Hand", value=f"{' '.join(dealer_cards)} = **{dealer_total}**", inline=True)
    embed.add_field(name="Result", value=result, inline=False)
    embed.add_field(name="Balance", value=f"🪙 {new_coins:,} coins", inline=True)
    
    await interaction.response.send_message(embed=embed)

async def show_roulette_game(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    min_bet = CASINO_GAMES["roulette"]["min_bet"]
    
    if player["coins"] < min_bet:
        await interaction.response.send_message(f"You need at least {min_bet} coins to play roulette!", ephemeral=True)
        return
    
    bet = min(50, player["coins"])
    result_num = random.randint(0, 36)
    is_red = result_num in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
    color_emoji = "🔴" if is_red else "⚫" if result_num != 0 else "🟢"
    
    bet_on_red = random.choice([True, False])
    
    if result_num == 0:
        winnings = 0
        result = "💔 Green 0! House wins."
        color = 0xFF0000
    elif (bet_on_red and is_red) or (not bet_on_red and not is_red):
        winnings = bet * 2
        result = f"🎉 You bet {'red' if bet_on_red else 'black'} and won!"
        color = 0x00FF00
    else:
        winnings = 0
        result = f"💔 You bet {'red' if bet_on_red else 'black'} and lost."
        color = 0xFF0000
    
    new_coins = player["coins"] - bet + winnings
    if winnings > 0:
        await update_player(interaction.user.id, coins=new_coins, casino_wins=player["casino_wins"] + 1)
    else:
        await update_player(interaction.user.id, coins=new_coins, casino_losses=player["casino_losses"] + 1)
    
    embed = discord.Embed(title="🎡 Roulette", color=color)
    embed.add_field(name="Result", value=f"{color_emoji} **{result_num}**", inline=True)
    embed.add_field(name="Your Bet", value=f"{'🔴 Red' if bet_on_red else '⚫ Black'}", inline=True)
    embed.add_field(name="Outcome", value=result, inline=False)
    embed.add_field(name="Balance", value=f"🪙 {new_coins:,} coins", inline=True)
    
    await interaction.response.send_message(embed=embed)

async def show_dice_game(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    min_bet = CASINO_GAMES["dice"]["min_bet"]
    
    if player["coins"] < min_bet:
        await interaction.response.send_message(f"You need at least {min_bet} coins to play dice!", ephemeral=True)
        return
    
    bet = min(50, player["coins"])
    player_roll = random.randint(1, 6) + random.randint(1, 6)
    dealer_roll = random.randint(1, 6) + random.randint(1, 6)
    
    if player_roll > dealer_roll:
        winnings = bet * 2
        result = "🎉 You win!"
        color = 0x00FF00
    elif dealer_roll > player_roll:
        winnings = 0
        result = "💔 Dealer wins."
        color = 0xFF0000
    else:
        winnings = bet
        result = "🤝 Tie! Bet returned."
        color = 0xFFFF00
    
    new_coins = player["coins"] - bet + winnings
    if winnings > bet:
        await update_player(interaction.user.id, coins=new_coins, casino_wins=player["casino_wins"] + 1)
    elif winnings < bet:
        await update_player(interaction.user.id, coins=new_coins, casino_losses=player["casino_losses"] + 1)
    else:
        await update_player(interaction.user.id, coins=new_coins)
    
    embed = discord.Embed(title="🎲 Dice Roll", color=color)
    embed.add_field(name="Your Roll", value=f"🎲 **{player_roll}**", inline=True)
    embed.add_field(name="Dealer Roll", value=f"🎲 **{dealer_roll}**", inline=True)
    embed.add_field(name="Result", value=result, inline=False)
    embed.add_field(name="Balance", value=f"🪙 {new_coins:,} coins", inline=True)
    
    await interaction.response.send_message(embed=embed)

async def show_coinflip_game(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    min_bet = CASINO_GAMES["coinflip"]["min_bet"]
    
    if player["coins"] < min_bet:
        await interaction.response.send_message(f"You need at least {min_bet} coins to play coinflip!", ephemeral=True)
        return
    
    bet = min(100, player["coins"])
    result = random.choice(["heads", "tails"])
    player_choice = random.choice(["heads", "tails"])
    
    if result == player_choice:
        winnings = bet * 2
        result_text = f"🎉 It's {result}! You win!"
        color = 0x00FF00
    else:
        winnings = 0
        result_text = f"💔 It's {result}. You lose."
        color = 0xFF0000
    
    new_coins = player["coins"] - bet + winnings
    if winnings > 0:
        await update_player(interaction.user.id, coins=new_coins, casino_wins=player["casino_wins"] + 1)
    else:
        await update_player(interaction.user.id, coins=new_coins, casino_losses=player["casino_losses"] + 1)
    
    embed = discord.Embed(title="🪙 Coin Flip", color=color)
    embed.add_field(name="Your Call", value=f"{'🪙' if player_choice == 'heads' else '💫'} {player_choice.title()}", inline=True)
    embed.add_field(name="Result", value=f"{'🪙' if result == 'heads' else '💫'} {result.title()}", inline=True)
    embed.add_field(name="Outcome", value=result_text, inline=False)
    embed.add_field(name="Balance", value=f"🪙 {new_coins:,} coins", inline=True)
    
    await interaction.response.send_message(embed=embed)

async def show_jobs_menu(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    
    embed = discord.Embed(title="💼 Job Center", description="Choose a job to earn coins and XP!", color=0x00FF00)
    embed.add_field(name="💰 Your Stats", value=f"Coins: 🪙 **{player['coins']:,}**\nLevel: **{player['level']}**\nTotal Earnings: 🪙 **{player['total_earnings']:,}**", inline=False)
    
    job_list = []
    for job_id, job_data in JOBS.items():
        min_level = job_data.get("min_level", 1)
        locked = player["level"] < min_level
        status = f"🔒 Lv.{min_level}" if locked else "✅"
        job_list.append(f"{job_data['emoji']} **{job_data['name']}** {status}\n*{job_data['description']}*\nPay: 🪙 {job_data['base_pay']} | XP: {job_data['xp']}")
    
    embed.add_field(name="Available Jobs", value="\n\n".join(job_list[:3]), inline=False)
    if len(job_list) > 3:
        embed.add_field(name="More Jobs", value="\n\n".join(job_list[3:]), inline=False)
    
    view = JobsView(interaction.user.id, player["level"])
    try:
        await interaction.response.send_message(embed=embed, view=view)
    except:
        await interaction.followup.send(embed=embed, view=view)

async def do_work(interaction: discord.Interaction, job_id: str):
    player = await get_or_create_player(interaction.user.id)
    job = JOBS.get(job_id)
    
    if not job:
        await interaction.response.send_message("Invalid job!", ephemeral=True)
        return
    
    min_level = job.get("min_level", 1)
    if player["level"] < min_level:
        await interaction.response.send_message(f"You need level {min_level} for this job!", ephemeral=True)
        return
    
    time_since = time.time() - player["last_work_time"]
    if time_since < job["cooldown"]:
        remaining = int(job["cooldown"] - time_since)
        mins = remaining // 60
        secs = remaining % 60
        await interaction.response.send_message(f"You're tired! Wait **{mins}m {secs}s** before working again.", ephemeral=True)
        return
    
    coins_earned = job["base_pay"] + random.randint(-10, 50)
    xp_earned = job["xp"] + random.randint(-5, 20)
    bonus_chance = random.random()
    bonus_text = ""
    
    if bonus_chance < 0.1:
        bonus_coins = coins_earned
        coins_earned += bonus_coins
        bonus_text = f"\n🌟 **BONUS!** Extra {bonus_coins} coins!"
    
    new_xp = player["xp"] + xp_earned
    new_level = calculate_level(new_xp)
    level_up = new_level > player["level"]
    
    await update_player(
        interaction.user.id,
        coins=player["coins"] + coins_earned,
        xp=new_xp,
        level=new_level,
        last_work_time=time.time(),
        total_earnings=player["total_earnings"] + coins_earned
    )
    
    embed = discord.Embed(title=f"{job['emoji']} Working as {job['name']}", color=0x00FF00)
    embed.add_field(name="Work Complete!", value=f"You worked hard and earned rewards!{bonus_text}", inline=False)
    embed.add_field(name="Earnings", value=f"🪙 +{coins_earned:,} coins\n⭐ +{xp_earned:,} XP", inline=True)
    embed.add_field(name="Balance", value=f"🪙 {player['coins'] + coins_earned:,}", inline=True)
    
    if level_up:
        embed.add_field(name="⬆️ LEVEL UP!", value=f"You are now level **{new_level}**!", inline=False)
    
    embed.set_footer(text=f"Cooldown: {job['cooldown'] // 60}m | Next work in {job['cooldown'] // 60} minutes")
    
    await interaction.response.send_message(embed=embed)

async def show_music_menu(interaction: discord.Interaction):
    embed = discord.Embed(title="🎵 Music Player", description="Play music from YouTube or Spotify!", color=0x1DB954)
    embed.add_field(name="How to Play", value="Use `/play <link or search>` to play music!\n\nSupported:\n• YouTube videos & playlists\n• Spotify tracks & playlists\n• Search by song name", inline=False)
    embed.add_field(name="Controls", value="`/play` - Play a song\n`/pause` - Pause playback\n`/resume` - Resume playback\n`/skip` - Skip current song\n`/stop` - Stop and leave", inline=False)
    embed.set_footer(text="Join a voice channel first!")
    
    try:
        await interaction.response.send_message(embed=embed)
    except:
        await interaction.followup.send(embed=embed)

async def show_profile(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    pets = await get_player_pets(interaction.user.id)
    chests = await get_player_chests(interaction.user.id)
    equipped_charms = await get_equipped_charms(interaction.user.id)
    
    xp_into, xp_needed = xp_to_next_level(player["xp"], player["level"])
    progress = min(20, int((xp_into / max(1, xp_needed)) * 20))
    bar = "█" * progress + "░" * (20 - progress)
    
    biome = BIOMES[player["current_biome"]]
    rod = RODS[player["rod_level"]]
    boat = BOATS[player["boat_level"]]
    
    embed = discord.Embed(title=f"👤 {interaction.user.display_name}'s Profile", color=0x00AAFF)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    
    embed.add_field(name="📊 Level & XP", value=f"**Level {player['level']}** (P{player['prestige']})\n[{bar}]\n{xp_into:,} / {xp_needed:,} XP", inline=True)
    embed.add_field(name="💰 Wealth", value=f"🪙 **{player['coins']:,}** coins\nTotal Earned: {player['total_earnings']:,}", inline=True)
    embed.add_field(name="🐟 Fishing", value=f"Fish Caught: **{player['total_fish']:,}**\nBiome: {biome['emoji']} {biome['name']}", inline=True)
    
    embed.add_field(name="🔧 Equipment", value=f"{rod['emoji']} **{rod['name']}**\n{boat['emoji']} **{boat['name']}**", inline=True)
    
    if pets:
        pet_text = " ".join([next((p["emoji"] for p in PETS if p["id"] == pid), "") for pid in pets[:5]])
        embed.add_field(name=f"🐾 Pets ({len(pets)}/{len(PETS)})", value=pet_text or "None", inline=True)
    
    if chests:
        total_chests = sum(chests.values())
        embed.add_field(name="📦 Chests", value=f"**{total_chests}** total", inline=True)
    
    embed.add_field(name="🎰 Casino Stats", value=f"Wins: **{player['casino_wins']}**\nLosses: **{player['casino_losses']}**", inline=True)
    
    unlocked_biomes = sum(1 for b in BIOMES.values() if player["level"] >= b["min_level"])
    embed.add_field(name="🌍 Biomes", value=f"**{unlocked_biomes}/{len(BIOMES)}** unlocked", inline=True)
    
    try:
        await interaction.response.send_message(embed=embed)
    except:
        await interaction.followup.send(embed=embed)

async def show_tutorials_menu(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Tutorials & Help", description="Learn how to use all the bot features!", color=0x9B59B6)
    embed.add_field(name="Choose a Tutorial", value="Click a button below to learn about each feature.", inline=False)
    embed.add_field(name="Quick Commands", value="`/home` - Main menu\n`/fish` - Go fishing\n`/work` - Do a job\n`/play` - Play music\n`/talk` - Chat with AI", inline=False)
    
    view = TutorialView(interaction.user.id)
    try:
        await interaction.response.send_message(embed=embed, view=view)
    except:
        await interaction.followup.send(embed=embed, view=view)

async def show_shop_menu(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    
    embed = discord.Embed(title="🛒 Equipment Shop", description="Upgrade your gear to catch better fish!", color=0xFFD700)
    embed.add_field(name="💰 Your Coins", value=f"🪙 **{player['coins']:,}**", inline=False)
    
    current_rod = RODS[player["rod_level"]]
    if player["rod_level"] < len(RODS):
        next_rod = RODS[player["rod_level"] + 1]
        rod_text = f"Current: {current_rod['emoji']} {current_rod['name']}\nNext: {next_rod['emoji']} {next_rod['name']} (🪙 {next_rod['cost']:,})"
    else:
        rod_text = f"Current: {current_rod['emoji']} {current_rod['name']} (MAX)"
    
    current_boat = BOATS[player["boat_level"]]
    if player["boat_level"] < len(BOATS):
        next_boat = BOATS[player["boat_level"] + 1]
        boat_text = f"Current: {current_boat['emoji']} {current_boat['name']}\nNext: {next_boat['emoji']} {next_boat['name']} (🪙 {next_boat['cost']:,})"
    else:
        boat_text = f"Current: {current_boat['emoji']} {current_boat['name']} (MAX)"
    
    embed.add_field(name="🎣 Rod", value=rod_text, inline=True)
    embed.add_field(name="🚤 Boat", value=boat_text, inline=True)
    
    if player["level"] >= 50:
        embed.add_field(name="⭐ Prestige", value=f"Available! Current: P{player['prestige']}\nGain +5% permanent bonus!", inline=False)
    else:
        embed.add_field(name="⭐ Prestige", value=f"Reach level 50 to prestige!\nCurrent: Level {player['level']}/50", inline=False)
    
    view = ShopView(interaction.user.id)
    try:
        await interaction.response.send_message(embed=embed, view=view)
    except:
        await interaction.followup.send(embed=embed, view=view)

async def show_settings_menu(interaction: discord.Interaction):
    embed = discord.Embed(title="⚙️ Settings", description="Manage your account settings.", color=0x808080)
    embed.add_field(name="🗑️ Reset Data", value="Delete all your progress and start fresh.", inline=False)
    embed.add_field(name="🧠 Clear AI Memory", value="Make the AI forget your conversations.", inline=False)
    
    view = SettingsView(interaction.user.id)
    try:
        await interaction.response.send_message(embed=embed, view=view)
    except:
        await interaction.followup.send(embed=embed, view=view)

async def generate_ai_response(user_id: int, username: str, message: str) -> str:
    if not openai_client:
        return "AI chat is not available. Please ask the bot owner to add an OpenAI API key."
    
    memory = await get_ai_memory(user_id)
    
    system_prompt = f"""You are a friendly, helpful AI assistant in a Discord bot. You're talking to {username}.

You remember past conversations and learn from them. Here's what you know about this user:
- Personality traits you've observed: {memory['personality'] or 'Still learning about them'}
- Topics they've discussed: {', '.join(memory['topics'][-10:]) if memory['topics'] else 'None yet'}
- Facts they've shared: {', '.join(memory['learned_facts'][-10:]) if memory['learned_facts'] else 'None yet'}
- Their current mood seems: {memory['mood']}
- You've had {memory['interaction_count']} conversations with them

Be conversational, remember details they share, and adapt to their communication style.
If they share personal information or preferences, acknowledge and remember them.
Keep responses concise but engaging (2-3 sentences usually).
Use emojis occasionally to be friendly but don't overdo it."""

    messages = [{"role": "system", "content": system_prompt}]
    
    for old_msg in memory['last_messages'][-6:]:
        messages.append(old_msg)
    
    messages.append({"role": "user", "content": message})
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-5",
            messages=messages,
            max_completion_tokens=256
        )
        ai_response = response.choices[0].message.content
        
        new_messages = memory['last_messages'][-8:] + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": ai_response}
        ]
        
        new_topics = memory['topics']
        words = message.lower().split()
        topics_keywords = ["like", "love", "hate", "prefer", "enjoy", "want", "need", "think", "feel", "believe"]
        for i, word in enumerate(words):
            if word in topics_keywords and i + 1 < len(words):
                potential_topic = words[i + 1]
                if len(potential_topic) > 3 and potential_topic not in new_topics:
                    new_topics.append(potential_topic)
        
        new_facts = memory['learned_facts']
        fact_indicators = ["my name is", "i am", "i'm", "i live", "i work", "i like", "my favorite"]
        for indicator in fact_indicators:
            if indicator in message.lower():
                new_facts.append(message[:100])
                break
        
        await update_ai_memory(
            user_id,
            topics=new_topics[-20:],
            last_messages=new_messages[-10:],
            learned_facts=new_facts[-20:],
            interaction_count=memory['interaction_count'] + 1,
            last_interaction=time.time()
        )
        
        return ai_response
    except Exception as e:
        return f"Sorry, I'm having trouble thinking right now. Error: {str(e)[:100]}"

async def show_upgrades_menu(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    rod = RODS[player["rod_level"]]
    boat = BOATS[player["boat_level"]]
    
    embed = discord.Embed(title="🔧 Equipment Upgrades", description="Improve your gear to catch better fish and earn more XP!", color=0x00FF88)
    embed.add_field(name="Current Rod", value=f"{rod['emoji']} **{rod['name']}**", inline=True)
    embed.add_field(name="Current Boat", value=f"{boat['emoji']} **{boat['name']}**", inline=True)
    embed.add_field(name="Balance", value=f"🪙 **{player['coins']:,}** coins", inline=False)
    
    view = ShopView(interaction.user.id)
    if interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=embed, view=view)

caregiver_assignments = {}
caregiver_history = {} # user_id: list of messages
roleplay_assignments = {}
roleplay_history = {} # user_id: list of messages

async def save_ai_session(user_id, session_type, prompt, history, is_active=1):
    async with aiosqlite.connect(DB_PATH) as db:
        # Self-healing: Ensure table exists before any write
        await db.execute("""CREATE TABLE IF NOT EXISTS ai_sessions (
            user_id INTEGER PRIMARY KEY,
            type TEXT,
            prompt TEXT,
            history TEXT,
            is_active INTEGER DEFAULT 1
        )""")
        history_json = json.dumps(history)
        await db.execute("""INSERT OR REPLACE INTO ai_sessions (user_id, type, prompt, history, is_active)
                           VALUES (?, ?, ?, ?, ?)""", (user_id, session_type, prompt, history_json, is_active))
        await db.commit()

async def load_ai_sessions():
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if table exists before loading
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_sessions'")
        if not await cursor.fetchone():
            await db.execute("""CREATE TABLE IF NOT EXISTS ai_sessions (
                user_id INTEGER PRIMARY KEY,
                type TEXT,
                prompt TEXT,
                history TEXT,
                is_active INTEGER DEFAULT 1
            )""")
            await db.commit()
            return

        async with db.execute("SELECT user_id, type, prompt, history, is_active FROM ai_sessions") as cursor:
            async for row in cursor:
                user_id, s_type, prompt, history_json, is_active = row
                history = json.loads(history_json)
                if is_active:
                    if s_type == 'caregiver':
                        caregiver_assignments[user_id] = True
                        caregiver_history[user_id] = history
                    else:
                        roleplay_assignments[user_id] = prompt
                        roleplay_history[user_id] = history

@bot.tree.command(name="caregiver", description="Assign Harry to be a caregiver for someone (Admin only)")
@app_commands.describe(user="The user Harry will take care of")
@app_commands.checks.has_permissions(manage_guild=True)
async def caregiver_command(interaction: discord.Interaction, user: discord.Member):
    if user.id in roleplay_assignments:
        del roleplay_assignments[user.id]
        if user.id in roleplay_history: del roleplay_history[user.id]
            
    caregiver_assignments[user.id] = True
    caregiver_history[user.id] = []
    await save_ai_session(user.id, 'caregiver', '', [])
    embed = discord.Embed(title="🍼 Caregiver Assigned", description=f"Harry is now taking care of {user.mention}!", color=0xFFB6C1)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="roleplay", description="Assign Harry to roleplay with someone (Admin only)")
@app_commands.describe(user="The user Harry will roleplay with", prompt="Custom roleplay instructions/context")
@app_commands.checks.has_permissions(manage_guild=True)
async def roleplay_command(interaction: discord.Interaction, user: discord.Member, prompt: str):
    if user.id in caregiver_assignments:
        del caregiver_assignments[user.id]
        if user.id in caregiver_history: del caregiver_history[user.id]
            
    roleplay_assignments[user.id] = prompt
    roleplay_history[user.id] = []
    await save_ai_session(user.id, 'roleplay', prompt, [])
    embed = discord.Embed(title="🎭 Roleplay Started", description=f"Harry is now roleplaying with {user.mention}!", color=0x9B59B6)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pause_ai", description="Pause an active AI session (Admin only)")
@app_commands.checks.has_permissions(manage_guild=True)
async def pause_ai_command(interaction: discord.Interaction, user: discord.Member):
    s_type = None
    prompt = ''
    history = []
    if user.id in caregiver_assignments:
        s_type = 'caregiver'
        history = caregiver_history.get(user.id, [])
        del caregiver_assignments[user.id]
    elif user.id in roleplay_assignments:
        s_type = 'roleplay'
        prompt = roleplay_assignments[user.id]
        history = roleplay_history.get(user.id, [])
        del roleplay_assignments[user.id]
    
    if s_type:
        await save_ai_session(user.id, s_type, prompt, history, is_active=0)
        await interaction.response.send_message(f"⏸️ Paused AI session for {user.mention}.")
    else:
        await interaction.response.send_message("No active session found.", ephemeral=True)

@bot.tree.command(name="resume_ai", description="Resume a paused AI session (Admin only)")
@app_commands.checks.has_permissions(manage_guild=True)
async def resume_ai_command(interaction: discord.Interaction, user: discord.Member):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT type, prompt, history FROM ai_sessions WHERE user_id = ?", (user.id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                s_type, prompt, history_json = row
                history = json.loads(history_json)
                if s_type == 'caregiver':
                    caregiver_assignments[user.id] = True
                    caregiver_history[user.id] = history
                else:
                    roleplay_assignments[user.id] = prompt
                    roleplay_history[user.id] = history
                await db.execute("UPDATE ai_sessions SET is_active = 1 WHERE user_id = ?", (user.id,))
                await db.commit()
                await interaction.response.send_message(f"▶️ Resumed {s_type} session for {user.mention}.")
            else:
                await interaction.response.send_message("No saved session found.", ephemeral=True)

@bot.tree.command(name="stop_ai", description="Stop and delete an AI session (Admin only)")
@app_commands.checks.has_permissions(manage_guild=True)
async def stop_ai_command(interaction: discord.Interaction, user: discord.Member):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM ai_sessions WHERE user_id = ?", (user.id,))
        await db.commit()
    caregiver_assignments.pop(user.id, None)
    roleplay_assignments.pop(user.id, None)
    await interaction.response.send_message(f"🛑 Stopped and deleted AI session for {user.mention}.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Handle DMs for the assistant
    if isinstance(message.channel, discord.DMChannel):
        user_id = message.author.id
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT prompt, history, is_active, type FROM ai_sessions WHERE user_id = ?", (user_id,))
            session = await cur.fetchone()
            
            if session:
                prompt, history_json, active_state, session_type = session
                
                # Check if this is an assistant session
                if not session_type.startswith("assistant"):
                    if session_type != "assistant":
                         pass # Not an assistant session
                    else:
                        pass # Default assistant
                
                # If they say "menu", force show the menu and reset active state to 1
                if message.content.lower() == "menu" or active_state == 1:
                    if active_state != 1:
                        await db.execute("UPDATE ai_sessions SET is_active = 1, type = 'assistant' WHERE user_id = ?", (user_id,))
                        await db.commit()
                    
                    view = AssistantView(user_id)
                    embed = discord.Embed(title="🤖 Assistant Menu", description="How would you like to interact today?", color=0x7289DA)
                    await message.channel.send(embed=embed, view=view)
                    return

                # If state is 2, it means a mode is active and we should reply
                if active_state == 2:
                    mode = session_type.split("_")[1] if "_" in session_type else "chatting"
                    await log_conversation(user_id, message.author.name, mode, "user", message.content)
                    
                    history = json.loads(history_json) if history_json else []
                    history.append({"role": "user", "content": message.content})
                    if len(history) > 20: history = history[-20:]
                    
                    api_key = os.getenv("OPENROUTER_API_KEY")
                    if api_key:
                        from openai import OpenAI
                        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
                        messages = [{"role": "system", "content": prompt}] + history
                        
                        try:
                            async with message.channel.typing():
                                completion = client.chat.completions.create(
                                    model="google/gemini-2.0-flash-001",
                                    messages=messages,
                                )
                                response = completion.choices[0].message.content
                                await log_conversation(user_id, message.author.name, mode, "assistant", response)
                                
                                history.append({"role": "assistant", "content": response})
                                await db.execute("UPDATE ai_sessions SET history = ? WHERE user_id = ?", 
                                               (json.dumps(history), user_id))
                                await db.commit()
                                
                                for i in range(0, len(response), 2000):
                                    await message.channel.send(response[i:i+2000])
                            return
                        except Exception as e:
                            await message.channel.send(f"Sorry, I had a bit of trouble thinking. Error: {str(e)[:100]}")
                            return
                    else:
                        await message.channel.send("I'm here for you! (AI features are currently limited without an API key)")
                        return

    is_caregiver = message.author.id in caregiver_assignments
    is_roleplay = message.author.id in roleplay_assignments

    if is_caregiver or is_roleplay:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if api_key:
            try:
                from openai import OpenAI
                client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=api_key,
                )
                
                if is_caregiver:
                    system_prompt = (
                        "You are Harry, a warm, patient, and deeply supportive caregiver. "
                        "You are talking to someone who is currently in age regression. "
                        "Your tone should be gentle, safe, and nurturing. Use simple, comforting language. "
                        "Always prioritize their safety and emotional well-being."
                    )
                    history_dict = caregiver_history
                    s_type = 'caregiver'
                    prompt_val = ''
                else:
                    prompt_val = roleplay_assignments[message.author.id]
                    system_prompt = (
                        f"You are Harry, roleplaying with a user. Context/Instructions: {prompt_val} "
                        "Stay in character and follow the roleplay context provided. "
                        "Provide engaging and immersive responses."
                    )
                    history_dict = roleplay_history
                    s_type = 'roleplay'

                history = history_dict.get(message.author.id, [])
                history.append({"role": "user", "content": message.content})
                
                if len(history) > 10:
                    history = history[-10:]
                
                messages = [{"role": "system", "content": system_prompt}] + history
                
                completion = client.chat.completions.create(
                    extra_headers={
                        "HTTP-Referer": "https://replit.com",
                        "X-Title": "Ultimate Discord Bot",
                    },
                    model="google/gemini-2.0-flash-001",
                    messages=messages,
                )
                ai_response = completion.choices[0].message.content
                history.append({"role": "assistant", "content": ai_response})
                history_dict[message.author.id] = history
                
                # Save to DB after each message for persistence
                await save_ai_session(message.author.id, s_type, prompt_val, history)
                
                # Handle Discord's 2000 character limit by chunking
                if len(ai_response) <= 2000:
                    await message.reply(ai_response)
                else:
                    chunks = [ai_response[i:i+2000] for i in range(0, len(ai_response), 2000)]
                    for chunk in chunks:
                        await message.reply(chunk)
                return
            except Exception as e:
                print(f"AI Error: {e}")
        
        # Local fallback logic
        if any(word in message.content.lower() for word in ["help", "sad", "scared", "hungry", "tired"]):
            await message.reply("Don't worry, little one. I'm right here with you. Everything is going to be okay! 💖")
        elif "?" in message.content:
            await message.reply("That's a great question! I'm here to help you learn and feel safe. What else is on your mind? 🥰")
        else:
            await message.reply("I'm listening and I care about you! You're doing so well. ✨")

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    await init_db()
    await load_ai_sessions() # Restore sessions
    bot.loop.create_task(check_in_task()) # Start personal assistant task
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Failed to sync: {e}")

@bot.tree.command(name="home", description="Open the main menu dashboard")
async def home_command(interaction: discord.Interaction):
    await show_home(interaction)

@bot.tree.command(name="fish", description="Go fishing and catch fish!")
async def fish_command(interaction: discord.Interaction):
    await show_fishing_menu(interaction)

@bot.tree.command(name="casino", description="Visit the casino and play games!")
async def casino_command(interaction: discord.Interaction):
    await show_casino_menu(interaction)

@bot.tree.command(name="work", description="Do a job to earn coins!")
async def work_command(interaction: discord.Interaction):
    await show_jobs_menu(interaction)

@bot.tree.command(name="shop", description="Buy equipment upgrades")
async def shop_command(interaction: discord.Interaction):
    await show_shop_menu(interaction)

@bot.tree.command(name="profile", description="View your complete profile")
async def profile_command(interaction: discord.Interaction):
    await show_profile(interaction)

@bot.tree.command(name="tutorials", description="Learn how to use the bot")
async def tutorials_command(interaction: discord.Interaction):
    await show_tutorials_menu(interaction)

@bot.tree.command(name="reset", description="Reset your data and start fresh")
async def reset_command(interaction: discord.Interaction):
    embed = discord.Embed(title="⚠️ Reset All Data?", description="This will delete ALL your progress:\n- Level, XP, Coins\n- Fish inventory\n- Pets, Chests, Charms\n- AI memory\n\n**This cannot be undone!**", color=0xFF0000)
    view = ConfirmResetView(interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="talk", description="Chat with the AI that learns from you!")
@app_commands.describe(message="Your message to the AI")
async def talk_command(interaction: discord.Interaction, message: str):
    await interaction.response.defer()
    
    response = await generate_ai_response(interaction.user.id, interaction.user.display_name, message)
    
    embed = discord.Embed(title="🤖 AI Chat", color=0x7289DA)
    embed.add_field(name=f"💬 {interaction.user.display_name}", value=message[:1024], inline=False)
    embed.add_field(name="🤖 Bot", value=response[:1024], inline=False)
    
    memory = await get_ai_memory(interaction.user.id)
    embed.set_footer(text=f"Conversations: {memory['interaction_count']} | The more we chat, the better I understand you!")
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="slots", description="Play the slot machine!")
@app_commands.describe(bet="Amount to bet (default: 100)")
async def slots_command(interaction: discord.Interaction, bet: int = 100):
    player = await get_or_create_player(interaction.user.id)
    
    if bet < 10:
        await interaction.response.send_message("Minimum bet is 10 coins!", ephemeral=True)
        return
    if bet > player["coins"]:
        await interaction.response.send_message(f"You only have {player['coins']} coins!", ephemeral=True)
        return
    if bet > 10000:
        await interaction.response.send_message("Maximum bet is 10,000 coins!", ephemeral=True)
        return
    
    reels = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
    winnings = 0
    result = tuple(reels)
    
    if result in SLOT_PAYOUTS:
        winnings = bet * SLOT_PAYOUTS[result]
    elif reels[0] == reels[1] or reels[1] == reels[2]:
        winnings = bet
    
    new_coins = player["coins"] - bet + winnings
    if winnings > 0:
        await update_player(interaction.user.id, coins=new_coins, casino_wins=player["casino_wins"] + 1)
        result_text = f"🎉 **YOU WON {winnings:,} coins!**"
        color = 0x00FF00
    else:
        await update_player(interaction.user.id, coins=new_coins, casino_losses=player["casino_losses"] + 1)
        result_text = f"💔 You lost {bet} coins..."
        color = 0xFF0000
    
    embed = discord.Embed(title="🎰 Slot Machine", color=color)
    embed.add_field(name="Reels", value=f"╔═══════════╗\n║  {reels[0]}  {reels[1]}  {reels[2]}  ║\n╚═══════════╝", inline=False)
    embed.add_field(name="Result", value=result_text, inline=False)
    embed.add_field(name="Balance", value=f"🪙 {new_coins:,} coins", inline=True)
    embed.add_field(name="Bet", value=f"🪙 {bet} coins", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="coinflip", description="Flip a coin and double your bet!")
@app_commands.describe(bet="Amount to bet", call="Heads or Tails")
@app_commands.choices(call=[
    app_commands.Choice(name="Heads", value="heads"),
    app_commands.Choice(name="Tails", value="tails"),
])
async def coinflip_command(interaction: discord.Interaction, bet: int, call: str):
    player = await get_or_create_player(interaction.user.id)
    
    if bet < 10:
        await interaction.response.send_message("Minimum bet is 10 coins!", ephemeral=True)
        return
    if bet > player["coins"]:
        await interaction.response.send_message(f"You only have {player['coins']} coins!", ephemeral=True)
        return
    
    result = random.choice(["heads", "tails"])
    
    if result == call:
        winnings = bet * 2
        new_coins = player["coins"] + bet
        await update_player(interaction.user.id, coins=new_coins, casino_wins=player["casino_wins"] + 1)
        result_text = f"🎉 It's **{result}**! You won **{winnings:,}** coins!"
        color = 0x00FF00
    else:
        new_coins = player["coins"] - bet
        await update_player(interaction.user.id, coins=new_coins, casino_losses=player["casino_losses"] + 1)
        result_text = f"💔 It's **{result}**. You lost **{bet}** coins..."
        color = 0xFF0000
    
    embed = discord.Embed(title="🪙 Coin Flip", color=color)
    embed.add_field(name="Your Call", value=f"{'🪙' if call == 'heads' else '💫'} {call.title()}", inline=True)
    embed.add_field(name="Result", value=f"{'🪙' if result == 'heads' else '💫'} {result.title()}", inline=True)
    embed.add_field(name="Outcome", value=result_text, inline=False)
    embed.add_field(name="Balance", value=f"🪙 {new_coins:,} coins", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="inventory", description="View your fish inventory")
async def inventory_command(interaction: discord.Interaction):
    inv = await get_player_inventory(interaction.user.id)
    if not inv:
        await interaction.response.send_message("Your inventory is empty! Go catch some fish! 🎣", ephemeral=True)
        return
    
    embed = discord.Embed(title="📦 Your Fish Collection", color=0x00AAFF)
    rarity_groups = {}
    total_value = 0
    
    for fish_name, rarity, qty in inv:
        if rarity not in rarity_groups:
            rarity_groups[rarity] = []
        rarity_groups[rarity].append(f"{fish_name} x{qty}")
        fish_data = next((f for f in FISH_DATA.get(rarity, []) if f["name"] == fish_name), None)
        if fish_data:
            total_value += fish_data["value"] * qty
    
    for rarity in ["mythic", "legendary", "epic", "rare", "uncommon", "common"]:
        if rarity in rarity_groups:
            embed.add_field(name=f"{rarity.title()} Fish", value="\n".join(rarity_groups[rarity]), inline=False)
    
    embed.set_footer(text=f"Total Value: 🪙 {total_value:,} | Use /sell to sell fish")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="sell", description="Sell fish from your inventory")
@app_commands.describe(fish_name="Name of fish to sell, or 'all' to sell everything")
async def sell_command(interaction: discord.Interaction, fish_name: str = "all"):
    user_id = interaction.user.id
    
    if fish_name.lower() == "all":
        inv = await get_player_inventory(user_id)
        if not inv:
            await interaction.response.send_message("Your inventory is empty!", ephemeral=True)
            return
        
        total_coins = 0
        total_fish = 0
        for fname, rarity, qty in inv:
            fish_data = next((f for f in FISH_DATA.get(rarity, []) if f["name"] == fname), None)
            if fish_data:
                total_coins += fish_data["value"] * qty
                total_fish += qty
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM fish_inventory WHERE user_id = ?", (user_id,))
            await db.commit()
        
        player = await get_or_create_player(user_id)
        await update_player(user_id, coins=player["coins"] + total_coins)
        
        embed = discord.Embed(title="💰 Fish Sold!", color=0x00FF00)
        embed.add_field(name="Sold", value=f"🐟 **{total_fish:,}** fish", inline=True)
        embed.add_field(name="Earned", value=f"🪙 **{total_coins:,}** coins", inline=True)
        embed.add_field(name="New Balance", value=f"🪙 **{player['coins'] + total_coins:,}**", inline=True)
        await interaction.response.send_message(embed=embed)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT fish_name, rarity, quantity FROM fish_inventory WHERE user_id = ? AND LOWER(fish_name) = LOWER(?)", (user_id, fish_name))
            row = await cur.fetchone()
            if not row:
                await interaction.response.send_message(f"You don't have any **{fish_name}**!", ephemeral=True)
                return
            
            fname, rarity, qty = row
            fish_data = next((f for f in FISH_DATA.get(rarity, []) if f["name"] == fname), None)
            if not fish_data:
                await interaction.response.send_message("Fish data not found!", ephemeral=True)
                return
            
            coins = fish_data["value"] * qty
            await db.execute("DELETE FROM fish_inventory WHERE user_id = ? AND fish_name = ?", (user_id, fname))
            await db.commit()
        
        player = await get_or_create_player(user_id)
        await update_player(user_id, coins=player["coins"] + coins)
        await interaction.response.send_message(f"Sold **{qty}x {fname}** for 🪙 **{coins:,}** coins!")

@bot.tree.command(name="biomes", description="View all fishing biomes")
async def biomes_command(interaction: discord.Interaction):
    player = await get_or_create_player(interaction.user.id)
    player_level = player["level"]
    
    embed = discord.Embed(title="🌍 Fishing Biomes", description="Unlock new biomes by leveling up!", color=0x00AAFF)
    
    for biome_key, biome_data in list(BIOMES.items())[:12]:
        unlocked = player_level >= biome_data["min_level"]
        status = "✅ UNLOCKED" if unlocked else f"🔒 Lv.{biome_data['min_level']}"
        value = f"{biome_data['description']}\nFish: {int(biome_data['fish_bonus']*100)}% | Rare: {int(biome_data['rare_bonus']*100)}%\n{status}"
        embed.add_field(name=f"{biome_data['emoji']} {biome_data['name']}", value=value, inline=True)
    
    embed.set_footer(text=f"Your Level: {player_level} | Current: {BIOMES[player['current_biome']]['name']}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pets", description="View your pet collection")
async def pets_command(interaction: discord.Interaction):
    user_pets = await get_player_pets(interaction.user.id)
    
    embed = discord.Embed(title="🐾 Pet Collection", color=0xFFB6C1)
    
    if not user_pets:
        embed.description = "You don't have any pets yet!\n\nPets are rare drops while fishing. Keep fishing to find them!"
    else:
        owned_text = []
        for pet_id in user_pets:
            pet = next((p for p in PETS if p["id"] == pet_id), None)
            if pet:
                owned_text.append(f"{pet['emoji']} **{pet['name']}** — +{int(pet['value']*100)}% {pet['bonus']}")
        embed.add_field(name=f"Your Pets ({len(user_pets)}/{len(PETS)})", value="\n".join(owned_text), inline=False)
    
    missing = [p for p in PETS if p["id"] not in user_pets]
    if missing:
        missing_text = [f"{p['emoji']} {p['name']} (1 in {p['rarity']:,})" for p in missing[:5]]
        embed.add_field(name="Undiscovered Pets", value="\n".join(missing_text), inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="chests", description="View your treasure chests")
async def chests_command(interaction: discord.Interaction):
    chests = await get_player_chests(interaction.user.id)
    
    embed = discord.Embed(title="📦 Treasure Chests", color=0xFFAA00)
    
    if not chests:
        embed.description = "You don't have any chests yet!\n\nChests are rare drops while fishing. Keep fishing!"
    else:
        chest_text = []
        for chest_type, quantity in chests.items():
            chest_data = CHESTS.get(chest_type, {})
            chest_text.append(f"{chest_data.get('emoji', '📦')} **{chest_data.get('name', chest_type)}** x{quantity}")
        embed.add_field(name="Your Chests", value="\n".join(chest_text), inline=False)
        embed.add_field(name="Open Chests", value="Use `/openchest <type>` to open!", inline=False)
    
    chest_info = "\n".join([f"{c['emoji']} {c['name']} — 1 in {c['drop_rate']:,}" for c in CHESTS.values()])
    embed.add_field(name="Chest Rarities", value=chest_info, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="openchest", description="Open a treasure chest")
@app_commands.describe(chest_type="Type of chest to open")
@app_commands.choices(chest_type=[
    app_commands.Choice(name="Wooden Chest", value="wooden"),
    app_commands.Choice(name="Iron Chest", value="iron"),
    app_commands.Choice(name="Golden Chest", value="golden"),
    app_commands.Choice(name="Diamond Chest", value="diamond"),
    app_commands.Choice(name="Mythic Chest", value="mythic"),
    app_commands.Choice(name="Void Chest", value="void"),
])
async def openchest_command(interaction: discord.Interaction, chest_type: str):
    user_id = interaction.user.id
    
    if not await remove_chest_from_player(user_id, chest_type):
        await interaction.response.send_message(f"You don't have any {CHESTS[chest_type]['name']}!", ephemeral=True)
        return
    
    chest_data = CHESTS[chest_type]
    rewards = CHEST_REWARDS[chest_type]
    
    xp_reward = random.randint(rewards["xp"][0], rewards["xp"][1])
    coin_reward = random.randint(rewards["coins"][0], rewards["coins"][1])
    
    charm_found = None
    if random.random() < rewards["charm_chance"]:
        charm_found = random.choice(CHARMS)
    
    player = await get_or_create_player(user_id)
    new_xp = player["xp"] + xp_reward
    new_level = calculate_level(new_xp)
    await update_player(user_id, xp=new_xp, level=new_level, coins=player["coins"] + coin_reward)
    
    embed = discord.Embed(title=f"{chest_data['emoji']} Opening {chest_data['name']}!", color=chest_data["color"])
    embed.add_field(name="Rewards", value=f"+{xp_reward:,} XP\n+{coin_reward:,} coins", inline=False)
    
    if charm_found:
        embed.add_field(name="🎉 CHARM FOUND!", value=f"{charm_found['emoji']} **{charm_found['name']}**\n+{int(charm_found['bonus_value']*100)}% {charm_found['bonus']}", inline=False)
    
    if new_level > player["level"]:
        embed.add_field(name="⬆️ LEVEL UP!", value=f"You are now level **{new_level}**!", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="View the global leaderboard")
@app_commands.describe(category="Leaderboard category")
@app_commands.choices(category=[
    app_commands.Choice(name="Level", value="level"),
    app_commands.Choice(name="Coins", value="coins"),
    app_commands.Choice(name="Fish Caught", value="total_fish"),
    app_commands.Choice(name="Casino Wins", value="casino_wins"),
])
async def leaderboard_command(interaction: discord.Interaction, category: str = "level"):
    async with aiosqlite.connect(DB_PATH) as db:
        if category == "level":
            cur = await db.execute("SELECT user_id, level, prestige FROM players ORDER BY prestige DESC, level DESC, xp DESC LIMIT 10")
            title = "🏆 Level Leaderboard"
        elif category == "coins":
            cur = await db.execute("SELECT user_id, coins FROM players ORDER BY coins DESC LIMIT 10")
            title = "💰 Richest Players"
        elif category == "total_fish":
            cur = await db.execute("SELECT user_id, total_fish FROM players ORDER BY total_fish DESC LIMIT 10")
            title = "🐟 Top Fishers"
        else:
            cur = await db.execute("SELECT user_id, casino_wins FROM players ORDER BY casino_wins DESC LIMIT 10")
            title = "🎰 Casino Champions"
        
        rows = await cur.fetchall()
    
    embed = discord.Embed(title=title, color=0xFFD700)
    
    if not rows:
        embed.description = "No players yet!"
    else:
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(rows):
            medal = medals[i] if i < 3 else f"#{i+1}"
            try:
                user = await bot.fetch_user(row[0])
                name = user.display_name
            except:
                name = f"User {row[0]}"
            
            if category == "level":
                lines.append(f"{medal} **{name}** — Lv.{row[1]} (P{row[2]})")
            elif category == "coins":
                lines.append(f"{medal} **{name}** — 🪙 {row[1]:,}")
            elif category == "total_fish":
                lines.append(f"{medal} **{name}** — 🐟 {row[1]:,}")
            else:
                lines.append(f"{medal} **{name}** — 🎰 {row[1]:,} wins")
        
        embed.description = "\n".join(lines)
    
    await interaction.response.send_message(embed=embed)

async def extract_spotify_info(url: str) -> Optional[dict]:
    """Extract track info from Spotify URL using regex parsing."""
    try:
        track_match = re.search(r'spotify\.com/track/([a-zA-Z0-9]+)', url)
        playlist_match = re.search(r'spotify\.com/playlist/([a-zA-Z0-9]+)', url)
        album_match = re.search(r'spotify\.com/album/([a-zA-Z0-9]+)', url)
        
        if track_match:
            return {"type": "track", "id": track_match.group(1)}
        elif playlist_match:
            return {"type": "playlist", "id": playlist_match.group(1)}
        elif album_match:
            return {"type": "album", "id": album_match.group(1)}
        return None
    except:
        return None

async def extract_youtube_info(url: str) -> Optional[dict]:
    """Extract video info from YouTube URL using yt_dlp."""
    if not yt_dlp:
        return None
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return {
                    "title": info.get("title", "Unknown"),
                    "duration": info.get("duration", 0),
                    "channel": info.get("uploader", "Unknown"),
                    "url": url
                }
    except Exception as e:
        return {"error": str(e)}
    return None

async def search_youtube(query: str) -> Optional[dict]:
    """Search YouTube for a query using yt_dlp."""
    if not yt_dlp:
        return None
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch1',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if info and 'entries' in info and info['entries']:
                entry = info['entries'][0]
                return {
                    "title": entry.get("title", "Unknown"),
                    "duration": entry.get("duration", 0),
                    "channel": entry.get("uploader", "Unknown"),
                    "url": entry.get("url", entry.get("webpage_url", ""))
                }
    except:
        pass
    return None

async def play_next(guild: discord.Guild, text_channel: discord.TextChannel):
    """Play the next song in the queue."""
    player = get_music_player(guild.id)
    if not player.voice_client or not player.voice_client.is_connected():
        return
    
    next_song = player.get_next()
    if not next_song:
        player.is_playing = False
        embed = discord.Embed(title="🎵 Queue Empty", description="No more songs in queue. Use `/play` to add more!", color=0x808080)
        await text_channel.send(embed=embed)
        return
    
    try:
        source = await YTDLSource.from_url(next_song['url'], loop=bot.loop, stream=True)
        if source:
            player.is_playing = True
            
            def after_playing(error):
                if error:
                    print(f"Player error: {error}")
                asyncio.run_coroutine_threadsafe(play_next(guild, text_channel), bot.loop)
            
            player.voice_client.play(source, after=after_playing)
            
            duration = source.duration or 0
            mins = duration // 60
            secs = duration % 60
            
            embed = discord.Embed(title="🎵 Now Playing", color=0x1DB954)
            embed.add_field(name="Song", value=f"**{source.title}**", inline=False)
            embed.add_field(name="Channel", value=source.uploader, inline=True)
            embed.add_field(name="Duration", value=f"{mins}:{secs:02d}" if duration else "Unknown", inline=True)
            if source.thumbnail:
                embed.set_thumbnail(url=source.thumbnail)
            embed.set_footer(text=f"Queue: {len(player.queue)} songs remaining")
            await text_channel.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=f"Could not play: {str(e)[:100]}", color=0xFF0000)
        await text_channel.send(embed=embed)
        asyncio.run_coroutine_threadsafe(play_next(guild, text_channel), bot.loop)

@bot.tree.command(name="play", description="Play music from YouTube or Spotify")
@app_commands.describe(query="YouTube/Spotify link or search term")
async def play_command(interaction: discord.Interaction, query: str):
    if not interaction.user.voice:
        await interaction.response.send_message("You need to be in a voice channel!", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    voice_channel = interaction.user.voice.channel
    player = get_music_player(interaction.guild.id)
    
    if not player.voice_client or not player.voice_client.is_connected():
        try:
            player.voice_client = await voice_channel.connect()
        except Exception as e:
            await interaction.followup.send(f"Could not join voice channel: {str(e)[:100]}", ephemeral=True)
            return
    elif player.voice_client.channel != voice_channel:
        await player.voice_client.move_to(voice_channel)
    
    search_query = query
    is_spotify = False
    
    if "spotify.com" in query:
        is_spotify = True
        spotify_info = await extract_spotify_info(query)
        if spotify_info and spotify_info["type"] == "track":
            search_query = f"spotify track {spotify_info['id']}"
        else:
            search_query = query
    
    embed = discord.Embed(title="🎵 Adding to Queue...", color=0x1DB954)
    
    try:
        if "youtube.com" in query or "youtu.be" in query:
            source = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        else:
            source = await YTDLSource.search(search_query if not is_spotify else query.split('/')[-1].split('?')[0], loop=bot.loop, stream=True)
        
        if source:
            song_data = {
                'title': source.title,
                'url': source.data.get('webpage_url', query),
                'duration': source.duration,
                'thumbnail': source.thumbnail,
                'uploader': source.uploader,
                'requested_by': interaction.user.id
            }
            
            if not player.is_playing:
                player.current = song_data
                player.is_playing = True
                
                def after_playing(error):
                    if error:
                        print(f"Player error: {error}")
                    asyncio.run_coroutine_threadsafe(play_next(interaction.guild, interaction.channel), bot.loop)
                
                player.voice_client.play(source, after=after_playing)
                
                duration = source.duration or 0
                mins = duration // 60
                secs = duration % 60
                
                embed = discord.Embed(title="🎵 Now Playing", color=0x1DB954)
                embed.add_field(name="Song", value=f"**{source.title}**", inline=False)
                embed.add_field(name="Channel", value=source.uploader, inline=True)
                embed.add_field(name="Duration", value=f"{mins}:{secs:02d}" if duration else "Unknown", inline=True)
                if source.thumbnail:
                    embed.set_thumbnail(url=source.thumbnail)
                if is_spotify:
                    embed.add_field(name="Source", value="Found via Spotify link search", inline=False)
            else:
                player.add_to_queue(song_data)
                
                duration = source.duration or 0
                mins = duration // 60
                secs = duration % 60
                
                embed = discord.Embed(title="➕ Added to Queue", color=0x00AAFF)
                embed.add_field(name="Song", value=f"**{source.title}**", inline=False)
                embed.add_field(name="Duration", value=f"{mins}:{secs:02d}" if duration else "Unknown", inline=True)
                embed.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
                if source.thumbnail:
                    embed.set_thumbnail(url=source.thumbnail)
            
            embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        else:
            embed = discord.Embed(title="❌ Not Found", description="Could not find that song. Try a different search term.", color=0xFF0000)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=f"An error occurred: {str(e)[:200]}", color=0xFF0000)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="skip", description="Skip the current song")
async def skip_command(interaction: discord.Interaction):
    player = get_music_player(interaction.guild.id)
    
    if not player.voice_client or not player.voice_client.is_playing():
        await interaction.response.send_message("Nothing is playing right now!", ephemeral=True)
        return
    
    player.voice_client.stop()
    await interaction.response.send_message("⏭️ Skipped the current song!")

@bot.tree.command(name="stop", description="Stop playback and clear the queue")
async def stop_command(interaction: discord.Interaction):
    player = get_music_player(interaction.guild.id)
    
    if not player.voice_client:
        await interaction.response.send_message("Not connected to a voice channel!", ephemeral=True)
        return
    
    player.clear_queue()
    player.is_playing = False
    
    if player.voice_client.is_playing():
        player.voice_client.stop()
    
    await player.voice_client.disconnect()
    player.voice_client = None
    
    await interaction.response.send_message("⏹️ Stopped playback and cleared the queue!")

@bot.tree.command(name="pause", description="Pause the current song")
async def pause_command(interaction: discord.Interaction):
    player = get_music_player(interaction.guild.id)
    
    if not player.voice_client or not player.voice_client.is_playing():
        await interaction.response.send_message("Nothing is playing right now!", ephemeral=True)
        return
    
    player.voice_client.pause()
    await interaction.response.send_message("⏸️ Paused!")

@bot.tree.command(name="resume", description="Resume the paused song")
async def resume_command(interaction: discord.Interaction):
    player = get_music_player(interaction.guild.id)
    
    if not player.voice_client:
        await interaction.response.send_message("Not connected to a voice channel!", ephemeral=True)
        return
    
    if player.voice_client.is_paused():
        player.voice_client.resume()
        await interaction.response.send_message("▶️ Resumed!")
    else:
        await interaction.response.send_message("Nothing is paused!", ephemeral=True)

@bot.tree.command(name="queue", description="View the music queue")
async def queue_command(interaction: discord.Interaction):
    player = get_music_player(interaction.guild.id)
    
    embed = discord.Embed(title="🎵 Music Queue", color=0x1DB954)
    
    if player.current:
        duration = player.current.get('duration', 0)
        mins = duration // 60 if duration else 0
        secs = duration % 60 if duration else 0
        embed.add_field(name="🎶 Now Playing", value=f"**{player.current['title']}**\nDuration: {mins}:{secs:02d}", inline=False)
    else:
        embed.add_field(name="🎶 Now Playing", value="Nothing playing", inline=False)
    
    if player.queue:
        queue_text = []
        for i, song in enumerate(player.queue[:10], 1):
            duration = song.get('duration', 0)
            mins = duration // 60 if duration else 0
            secs = duration % 60 if duration else 0
            queue_text.append(f"`{i}.` {song['title'][:40]}... ({mins}:{secs:02d})")
        embed.add_field(name=f"📋 Up Next ({len(player.queue)} songs)", value="\n".join(queue_text), inline=False)
        if len(player.queue) > 10:
            embed.set_footer(text=f"...and {len(player.queue) - 10} more songs")
    else:
        embed.add_field(name="📋 Up Next", value="Queue is empty. Use `/play` to add songs!", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="nowplaying", description="Show the currently playing song")
async def nowplaying_command(interaction: discord.Interaction):
    player = get_music_player(interaction.guild.id)
    
    if not player.current or not player.is_playing:
        await interaction.response.send_message("Nothing is playing right now!", ephemeral=True)
        return
    
    duration = player.current.get('duration', 0)
    mins = duration // 60 if duration else 0
    secs = duration % 60 if duration else 0
    
    embed = discord.Embed(title="🎵 Now Playing", color=0x1DB954)
    embed.add_field(name="Song", value=f"**{player.current['title']}**", inline=False)
    embed.add_field(name="Channel", value=player.current.get('uploader', 'Unknown'), inline=True)
    embed.add_field(name="Duration", value=f"{mins}:{secs:02d}" if duration else "Unknown", inline=True)
    if player.current.get('thumbnail'):
        embed.set_thumbnail(url=player.current['thumbnail'])
    embed.add_field(name="Queue", value=f"{len(player.queue)} songs remaining", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="trivia", description="Play a trivia game")
async def trivia_command(interaction: discord.Interaction):
    question_data = random.choice(TRIVIA_QUESTIONS)
    embed = discord.Embed(title="🧠 Trivia Time!", description=question_data["question"], color=0x9B59B6)
    options = question_data["options"]
    random.shuffle(options)
    for i, opt in enumerate(options):
        embed.add_field(name=f"{['A', 'B', 'C', 'D'][i]}", value=opt, inline=True)
    embed.set_footer(text="Type your answer (A, B, C, or D) in chat!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="riddle", description="Try to solve a riddle")
async def riddle_command(interaction: discord.Interaction):
    riddle_data = random.choice(RIDDLES)
    embed = discord.Embed(title="🤔 Riddle Me This!", description=riddle_data["riddle"], color=0xE74C3C)
    embed.set_footer(text=f"Answer: ||{riddle_data['answer']}|| (hover to reveal)")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="wouldyourather", description="Would you rather...")
async def wyr_command(interaction: discord.Interaction):
    choice = random.choice(WOULD_YOU_RATHER)
    embed = discord.Embed(title="🤷 Would You Rather...", color=0x3498DB)
    embed.add_field(name="Option A", value=f"**{choice[0]}**", inline=True)
    embed.add_field(name="VS", value="⚔️", inline=True)
    embed.add_field(name="Option B", value=f"**{choice[1]}**", inline=True)
    embed.set_footer(text="React with 🅰️ or 🅱️ to vote!")
    msg = await interaction.response.send_message(embed=embed)

@bot.tree.command(name="neverhaveiever", description="Never have I ever...")
async def nhie_command(interaction: discord.Interaction):
    statement = random.choice(NEVER_HAVE_I_EVER)
    embed = discord.Embed(title="🙈 Never Have I Ever...", description=f"**{statement}**", color=0xE91E63)
    embed.set_footer(text="React with ✅ if you have, ❌ if you haven't!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="truthordare", description="Truth or Dare?")
@app_commands.describe(choice="Pick truth or dare")
@app_commands.choices(choice=[app_commands.Choice(name="Truth", value="truth"), app_commands.Choice(name="Dare", value="dare")])
async def tod_command(interaction: discord.Interaction, choice: str):
    if choice == "truth":
        prompt = random.choice(TRUTH_PROMPTS)
        embed = discord.Embed(title="🔮 Truth!", description=prompt, color=0x2ECC71)
    else:
        prompt = random.choice(DARE_PROMPTS)
        embed = discord.Embed(title="🔥 Dare!", description=prompt, color=0xE74C3C)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="8ball", description="Ask the magic 8-ball a question")
@app_commands.describe(question="Your yes/no question")
async def eightball_command(interaction: discord.Interaction, question: str):
    responses = ["It is certain.", "It is decidedly so.", "Without a doubt.", "Yes definitely.", "You may rely on it.", "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.", "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.", "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful."]
    embed = discord.Embed(title="🎱 Magic 8-Ball", color=0x1F1F1F)
    embed.add_field(name="Question", value=question, inline=False)
    embed.add_field(name="Answer", value=f"**{random.choice(responses)}**", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="roll", description="Roll dice")
@app_commands.describe(dice="Dice notation (e.g., 2d6, d20)")
async def roll_command(interaction: discord.Interaction, dice: str = "d6"):
    try:
        parts = dice.lower().split("d")
        num_dice = int(parts[0]) if parts[0] else 1
        sides = int(parts[1]) if len(parts) > 1 else 6
        num_dice = min(num_dice, 100)
        sides = min(sides, 1000)
        rolls = [random.randint(1, sides) for _ in range(num_dice)]
        total = sum(rolls)
        embed = discord.Embed(title="🎲 Dice Roll", color=0x9B59B6)
        embed.add_field(name="Rolled", value=f"**{dice}**", inline=True)
        embed.add_field(name="Results", value=f"{rolls}" if len(rolls) <= 20 else f"[{len(rolls)} dice rolled]", inline=True)
        embed.add_field(name="Total", value=f"**{total}**", inline=True)
        await interaction.response.send_message(embed=embed)
    except:
        await interaction.response.send_message("Invalid dice format! Use format like `d6`, `2d20`, `4d8`", ephemeral=True)

@bot.tree.command(name="flip", description="Flip a coin")
async def flip_command(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    embed = discord.Embed(title="🪙 Coin Flip", description=f"**{result}!**", color=0xFFD700)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rps", description="Rock Paper Scissors")
@app_commands.describe(choice="Your choice")
@app_commands.choices(choice=[app_commands.Choice(name="Rock", value="rock"), app_commands.Choice(name="Paper", value="paper"), app_commands.Choice(name="Scissors", value="scissors")])
async def rps_command(interaction: discord.Interaction, choice: str):
    bot_choice = random.choice(["rock", "paper", "scissors"])
    emojis = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    wins = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
    if choice == bot_choice:
        result = "It's a tie!"
        color = 0xFFFF00
    elif wins[choice] == bot_choice:
        result = "You win!"
        color = 0x00FF00
    else:
        result = "You lose!"
        color = 0xFF0000
    embed = discord.Embed(title="✂️ Rock Paper Scissors", color=color)
    embed.add_field(name="You", value=f"{emojis[choice]} {choice.title()}", inline=True)
    embed.add_field(name="Bot", value=f"{emojis[bot_choice]} {bot_choice.title()}", inline=True)
    embed.add_field(name="Result", value=f"**{result}**", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="guess", description="Guess the number (1-100)")
async def guess_command(interaction: discord.Interaction):
    number = random.randint(1, 100)
    embed = discord.Embed(title="🔢 Number Guessing Game", description="I'm thinking of a number between 1 and 100!\nYou have 7 guesses. Type a number in chat!", color=0x3498DB)
    embed.set_footer(text=f"Secret: ||{number}|| (The answer is hidden)")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="hangman", description="Play hangman")
async def hangman_command(interaction: discord.Interaction):
    word = random.choice(WORD_LIST)
    hidden = " ".join(["_" for _ in word])
    embed = discord.Embed(title="🎯 Hangman", color=0x2ECC71)
    embed.add_field(name="Word", value=f"`{hidden}`", inline=False)
    embed.add_field(name="Hint", value=f"The word has **{len(word)}** letters", inline=True)
    embed.set_footer(text=f"Answer: ||{word}|| (hidden)")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="scramble", description="Unscramble the word")
async def scramble_command(interaction: discord.Interaction):
    word = random.choice(WORD_LIST)
    scrambled = "".join(random.sample(word, len(word)))
    while scrambled == word:
        scrambled = "".join(random.sample(word, len(word)))
    embed = discord.Embed(title="🔀 Word Scramble", description=f"Unscramble this word:\n\n**`{scrambled.upper()}`**", color=0xF39C12)
    embed.set_footer(text=f"Answer: ||{word}|| (hidden)")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="mathquiz", description="Quick math quiz")
async def mathquiz_command(interaction: discord.Interaction):
    num1 = random.randint(1, 50)
    num2 = random.randint(1, 50)
    op = random.choice(MATH_OPERATIONS)
    if op == "+":
        answer = num1 + num2
    elif op == "-":
        answer = num1 - num2
    else:
        num1 = random.randint(1, 12)
        num2 = random.randint(1, 12)
        answer = num1 * num2
    embed = discord.Embed(title="🧮 Math Quiz", description=f"What is **{num1} {op} {num2}**?", color=0x3498DB)
    embed.set_footer(text=f"Answer: ||{answer}|| (hidden)")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="typingrace", description="Typing speed challenge")
async def typingrace_command(interaction: discord.Interaction):
    sentences = ["The quick brown fox jumps over the lazy dog", "Pack my box with five dozen liquor jugs", "How vexingly quick daft zebras jump", "The five boxing wizards jump quickly", "Sphinx of black quartz judge my vow", "Two driven jocks help fax my big quiz", "Crazy Frederick bought many very exquisite opal jewels"]
    sentence = random.choice(sentences)
    embed = discord.Embed(title="⌨️ Typing Race", description="Type this sentence as fast as you can!", color=0xE74C3C)
    embed.add_field(name="Sentence", value=f"```{sentence}```", inline=False)
    embed.set_footer(text="Copy it exactly with correct capitalization and punctuation!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="emoji", description="Guess the emoji puzzle")
async def emoji_command(interaction: discord.Interaction):
    puzzles = [("🎬 + 🦁 + 👑", "The Lion King"), ("🧙‍♂️ + 💍 + 🗻", "Lord of the Rings"), ("🦸‍♂️ + 🦇", "Batman"), ("🚗 + 🏎️ + 💨", "Fast and Furious"), ("🧊 + ❄️ + 👸", "Frozen"), ("🌊 + 🚢 + 💔", "Titanic"), ("🦖 + 🏞️ + 🏃", "Jurassic Park"), ("🕷️ + 🧔", "Spider-Man"), ("⭐ + ⚔️ + 🌌", "Star Wars"), ("🧙‍♂️ + 👓 + ⚡", "Harry Potter")]
    puzzle = random.choice(puzzles)
    embed = discord.Embed(title="🎭 Emoji Movie Puzzle", description=f"Guess the movie:\n\n{puzzle[0]}", color=0x9B59B6)
    embed.set_footer(text=f"Answer: ||{puzzle[1]}|| (hidden)")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="quote", description="Get an inspirational quote")
async def quote_command(interaction: discord.Interaction):
    quotes = [("The only way to do great work is to love what you do.", "Steve Jobs"), ("Innovation distinguishes between a leader and a follower.", "Steve Jobs"), ("Stay hungry, stay foolish.", "Steve Jobs"), ("Life is what happens when you're busy making other plans.", "John Lennon"), ("The future belongs to those who believe in the beauty of their dreams.", "Eleanor Roosevelt"), ("It is during our darkest moments that we must focus to see the light.", "Aristotle"), ("The only thing we have to fear is fear itself.", "Franklin D. Roosevelt"), ("In the middle of difficulty lies opportunity.", "Albert Einstein"), ("Success is not final, failure is not fatal: it is the courage to continue that counts.", "Winston Churchill"), ("Believe you can and you're halfway there.", "Theodore Roosevelt")]
    quote = random.choice(quotes)
    embed = discord.Embed(title="💭 Inspirational Quote", description=f"*\"{quote[0]}\"*", color=0x9B59B6)
    embed.set_footer(text=f"— {quote[1]}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="joke", description="Get a random joke")
async def joke_command(interaction: discord.Interaction):
    jokes = ["Why don't scientists trust atoms? Because they make up everything!", "Why did the scarecrow win an award? He was outstanding in his field!", "What do you call a fake noodle? An impasta!", "Why don't eggs tell jokes? They'd crack each other up!", "What do you call a bear with no teeth? A gummy bear!", "Why did the bicycle fall over? Because it was two-tired!", "What do you call a fish without eyes? A fsh!", "Why don't skeletons fight each other? They don't have the guts!", "What do you call a sleeping dinosaur? A dino-snore!", "Why did the math book look so sad? Because it had too many problems!"]
    embed = discord.Embed(title="😂 Random Joke", description=random.choice(jokes), color=0xF1C40F)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fact", description="Get a random fun fact")
async def fact_command(interaction: discord.Interaction):
    facts = ["Honey never spoils. Archaeologists have found 3000-year-old honey that's still edible!", "A day on Venus is longer than its year.", "Octopuses have three hearts and blue blood.", "The shortest war in history lasted only 38-45 minutes.", "A group of flamingos is called a 'flamboyance'.", "Bananas are berries, but strawberries aren't.", "Cows have best friends and get stressed when separated.", "The moon is slowly drifting away from Earth.", "A single cloud can weigh more than 1 million pounds.", "Sharks have been around longer than trees."]
    embed = discord.Embed(title="🤓 Fun Fact", description=f"**Did you know?**\n\n{random.choice(facts)}", color=0x1ABC9C)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fortune", description="Get your fortune")
async def fortune_command(interaction: discord.Interaction):
    fortunes = ["A beautiful, smart, and loving person will be coming into your life.", "A dubious friend may be an enemy in camouflage.", "A faithful friend is a strong defense.", "A golden egg of opportunity falls into your lap this month.", "A lifetime of happiness lies ahead of you.", "Adventure can be real happiness.", "Believe in yourself and others will too.", "Change is happening in your life, so go with the flow!", "Don't be afraid to take that big step.", "Embrace this love relationship you have!"]
    embed = discord.Embed(title="🔮 Fortune Cookie", description=f"*{random.choice(fortunes)}*", color=0x9B59B6)
    embed.set_footer(text=f"Lucky numbers: {random.randint(1,50)}, {random.randint(1,50)}, {random.randint(1,50)}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="horoscope", description="Get your daily horoscope")
@app_commands.describe(sign="Your zodiac sign")
@app_commands.choices(sign=[app_commands.Choice(name=s, value=s.lower()) for s in ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]])
async def horoscope_command(interaction: discord.Interaction, sign: str):
    horoscopes = ["Today brings unexpected opportunities. Keep your eyes open!", "A creative surge will help you solve a lingering problem.", "Romance is in the air. Express your feelings boldly.", "Financial matters look favorable. Trust your instincts.", "Your social life gets a boost. Make new connections!", "Take time for self-care today. You deserve it.", "An old friend may reconnect with important news.", "Your hard work is about to pay off. Stay patient.", "Travel plans may shift. Be flexible and adaptable.", "Your intuition is especially strong today. Listen to it."]
    sign_emojis = {"aries": "♈", "taurus": "♉", "gemini": "♊", "cancer": "♋", "leo": "♌", "virgo": "♍", "libra": "♎", "scorpio": "♏", "sagittarius": "♐", "capricorn": "♑", "aquarius": "♒", "pisces": "♓"}
    embed = discord.Embed(title=f"{sign_emojis.get(sign, '⭐')} {sign.title()} Horoscope", description=random.choice(horoscopes), color=0x9B59B6)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="dadjoke", description="Get a dad joke")
async def dadjoke_command(interaction: discord.Interaction):
    jokes = ["I'm afraid for the calendar. Its days are numbered.", "I only know 25 letters of the alphabet. I don't know y.", "What did the ocean say to the beach? Nothing, it just waved.", "I'm reading a book about anti-gravity. It's impossible to put down!", "Did you hear about the claustrophobic astronaut? He just needed a little space.", "What do you call cheese that isn't yours? Nacho cheese!", "I used to hate facial hair, but then it grew on me.", "What do you call a fish without eyes? A fsh!", "I told my wife she was drawing her eyebrows too high. She looked surprised.", "Why don't scientists trust atoms? Because they make up everything!"]
    embed = discord.Embed(title="👔 Dad Joke", description=random.choice(jokes), color=0xF39C12)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pickup", description="Get a random pickup line")
async def pickup_command(interaction: discord.Interaction):
    lines = ["Are you a magician? Because whenever I look at you, everyone else disappears.", "Do you have a map? I keep getting lost in your eyes.", "Is your name Google? Because you have everything I've been searching for.", "Are you a parking ticket? Because you've got 'fine' written all over you.", "Do you believe in love at first sight, or should I walk by again?", "Is your dad a boxer? Because you're a knockout!", "Are you a camera? Because every time I look at you, I smile.", "If beauty were time, you'd be an eternity.", "I must be a snowflake, because I've fallen for you.", "Are you a bank loan? Because you've got my interest!"]
    embed = discord.Embed(title="💕 Pickup Line", description=f"*{random.choice(lines)}*", color=0xE91E63)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="roast", description="Get a friendly roast")
async def roast_command(interaction: discord.Interaction):
    roasts = ["You're not stupid; you just have bad luck thinking.", "I'd agree with you but then we'd both be wrong.", "You're like a cloud. When you disappear, it's a beautiful day.", "I'm not saying I hate you, but I would unplug your life support to charge my phone.", "You're proof that evolution can go in reverse.", "If you were any more inbred, you'd be a sandwich.", "You're not the dumbest person in the world, but you better hope they don't die.", "I'd explain it to you but I left my crayons at home.", "You have the right to remain silent because whatever you say will probably be stupid anyway.", "Light travels faster than sound. That's why you seemed bright until you spoke."]
    embed = discord.Embed(title="🔥 Friendly Roast", description=random.choice(roasts), color=0xE74C3C)
    embed.set_footer(text="(Just for fun, no offense meant!)")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="compliment", description="Get a compliment")
async def compliment_command(interaction: discord.Interaction):
    compliments = ["You're more helpful than you realize.", "You have the best laugh!", "You're an incredible friend.", "You light up the room.", "You have impeccable manners.", "I bet you sweat glitter.", "You were cool way before hipsters were cool.", "That thing you don't like about yourself is what makes you really interesting.", "You're a gift to those around you.", "You're even more beautiful on the inside than you are on the outside."]
    embed = discord.Embed(title="💖 Compliment", description=random.choice(compliments), color=0x2ECC71)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rate", description="Rate something out of 10")
@app_commands.describe(thing="What to rate")
async def rate_command(interaction: discord.Interaction, thing: str):
    rating = random.randint(0, 10)
    bars = "█" * rating + "░" * (10 - rating)
    embed = discord.Embed(title="⭐ Rating", color=0xF1C40F)
    embed.add_field(name="Subject", value=thing, inline=False)
    embed.add_field(name="Rating", value=f"**{rating}/10**\n[{bars}]", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ship", description="Ship two people together")
@app_commands.describe(person1="First person", person2="Second person")
async def ship_command(interaction: discord.Interaction, person1: str, person2: str):
    percentage = random.randint(0, 100)
    if percentage >= 80:
        status = "💕 Perfect Match!"
    elif percentage >= 60:
        status = "💖 Great Potential!"
    elif percentage >= 40:
        status = "💛 Could Work!"
    elif percentage >= 20:
        status = "💔 Needs Effort..."
    else:
        status = "💀 Not Meant To Be..."
    bars = "█" * (percentage // 10) + "░" * (10 - percentage // 10)
    embed = discord.Embed(title="💘 Love Calculator", color=0xE91E63)
    embed.add_field(name="Ship", value=f"**{person1}** ❤️ **{person2}**", inline=False)
    embed.add_field(name="Compatibility", value=f"**{percentage}%**\n[{bars}]", inline=False)
    embed.add_field(name="Status", value=status, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fight", description="Fight someone (for fun)")
@app_commands.describe(opponent="Who to fight")
async def fight_command(interaction: discord.Interaction, opponent: discord.Member):
    moves = ["👊 Punch", "🦶 Kick", "🤜 Uppercut", "💥 Slam", "🌀 Spinning Attack", "⚡ Lightning Strike", "🔥 Fire Blast", "❄️ Ice Freeze", "🌊 Tidal Wave", "☄️ Meteor Strike"]
    player_hp = 100
    opponent_hp = 100
    log = []
    while player_hp > 0 and opponent_hp > 0:
        move = random.choice(moves)
        damage = random.randint(10, 30)
        if random.choice([True, False]):
            opponent_hp -= damage
            log.append(f"{interaction.user.display_name} used {move} for **{damage}** damage!")
        else:
            player_hp -= damage
            log.append(f"{opponent.display_name} used {move} for **{damage}** damage!")
    winner = interaction.user.display_name if opponent_hp <= 0 else opponent.display_name
    embed = discord.Embed(title="⚔️ Epic Battle!", color=0xE74C3C)
    embed.add_field(name="Battle Log", value="\n".join(log[-5:]), inline=False)
    embed.add_field(name="Winner", value=f"🏆 **{winner}** wins!", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="slots2", description="Advanced slot machine")
async def slots2_command(interaction: discord.Interaction):
    symbols = ["🍎", "🍊", "🍋", "🍇", "🍉", "🍓", "🍒", "💎", "7️⃣", "⭐"]
    grid = [[random.choice(symbols) for _ in range(3)] for _ in range(3)]
    display = "\n".join([" | ".join(row) for row in grid])
    middle_row = grid[1]
    if middle_row[0] == middle_row[1] == middle_row[2]:
        result = f"🎉 JACKPOT! Triple {middle_row[0]}!"
        color = 0x00FF00
    elif middle_row[0] == middle_row[1] or middle_row[1] == middle_row[2]:
        result = "😊 Small win! Two matching!"
        color = 0xFFFF00
    else:
        result = "😔 No match. Try again!"
        color = 0xFF0000
    embed = discord.Embed(title="🎰 Advanced Slots", color=color)
    embed.add_field(name="Reels", value=f"```{display}```", inline=False)
    embed.add_field(name="Result", value=result, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="memory", description="Memory match game")
async def memory_command(interaction: discord.Interaction):
    pairs = ["🍎", "🍊", "🍋", "🍇"]
    cards = pairs * 2
    random.shuffle(cards)
    hidden = ["❓"] * 8
    embed = discord.Embed(title="🧠 Memory Game", description="Remember the positions!", color=0x9B59B6)
    embed.add_field(name="Cards (memorize!)", value=" ".join(cards), inline=False)
    embed.set_footer(text="Cards will be hidden in the next message!")
    await interaction.response.send_message(embed=embed)
    await asyncio.sleep(3)
    embed2 = discord.Embed(title="🧠 Memory Game", description="Now try to remember!", color=0x9B59B6)
    embed2.add_field(name="Hidden Cards", value=" ".join(hidden), inline=False)
    embed2.set_footer(text=f"Answer: ||{' '.join(cards)}||")
    await interaction.followup.send(embed=embed2)

@bot.tree.command(name="reaction", description="Reaction time test")
async def reaction_command(interaction: discord.Interaction):
    embed = discord.Embed(title="⏱️ Reaction Test", description="Wait for it... When you see 🟢, type `go` as fast as you can!", color=0xFF0000)
    await interaction.response.send_message(embed=embed)
    await asyncio.sleep(random.uniform(2, 5))
    embed2 = discord.Embed(title="⏱️ Reaction Test", description="🟢 **GO NOW!** Type `go` in chat!", color=0x00FF00)
    await interaction.followup.send(embed=embed2)

@bot.tree.command(name="pattern", description="Pattern recognition game")
async def pattern_command(interaction: discord.Interaction):
    patterns = [([1, 2, 4, 8, 16], 32, "Double each time"), ([1, 1, 2, 3, 5, 8], 13, "Fibonacci sequence"), ([2, 6, 18, 54], 162, "Multiply by 3"), ([3, 7, 11, 15, 19], 23, "Add 4"), ([1, 4, 9, 16, 25], 36, "Square numbers")]
    pattern = random.choice(patterns)
    embed = discord.Embed(title="🔢 Pattern Recognition", description="What comes next?", color=0x3498DB)
    embed.add_field(name="Sequence", value=f"**{', '.join(map(str, pattern[0]))}**, ?", inline=False)
    embed.set_footer(text=f"Answer: ||{pattern[1]} ({pattern[2]})||")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="wordchain", description="Start a word chain game")
async def wordchain_command(interaction: discord.Interaction):
    starters = ["apple", "elephant", "orange", "tiger", "rainbow", "winter", "summer", "music", "ocean", "galaxy"]
    word = random.choice(starters)
    embed = discord.Embed(title="🔗 Word Chain", description="Continue the chain! The next word must start with the last letter of the previous word.", color=0x2ECC71)
    embed.add_field(name="Starting Word", value=f"**{word}**", inline=False)
    embed.add_field(name="Next letter", value=f"Start your word with **{word[-1].upper()}**", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="categories", description="Name things in a category")
async def categories_command(interaction: discord.Interaction):
    categories = ["Countries that start with 'S'", "Fruits that are red", "Animals with 4 legs", "Things in a kitchen", "Types of sports", "Musical instruments", "Movie genres", "Pizza toppings", "Video game titles", "Famous scientists"]
    category = random.choice(categories)
    letter = random.choice("ABCDEFGHIJKLMNOPRSTW")
    embed = discord.Embed(title="📝 Categories Game", description=f"Name as many as you can!", color=0xE91E63)
    embed.add_field(name="Category", value=f"**{category}**", inline=False)
    embed.add_field(name="Challenge", value=f"Extra points if they start with **{letter}**!", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="acronym", description="Create an acronym game")
async def acronym_command(interaction: discord.Interaction):
    length = random.randint(3, 5)
    letters = "".join(random.choices("ABCDEFGHIJKLMNOPRSTW", k=length))
    embed = discord.Embed(title="📖 Acronym Game", description=f"Create a funny phrase for this acronym!", color=0xF39C12)
    embed.add_field(name="Acronym", value=f"**{letters}**", inline=False)
    embed.set_footer(text="Be creative! Each word must start with the corresponding letter.")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="storytime", description="Collaborative story game")
async def storytime_command(interaction: discord.Interaction):
    starters = ["Once upon a time, in a land far away,", "It was a dark and stormy night when", "Nobody expected what happened next:", "In the year 3000,", "Deep in the enchanted forest,", "The spaceship landed and", "With a flash of lightning,", "At the stroke of midnight,"]
    starter = random.choice(starters)
    embed = discord.Embed(title="📚 Story Time!", description="Continue the story! Add one sentence.", color=0x9B59B6)
    embed.add_field(name="Story Start", value=f"*{starter}*", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="tictactoe", description="Play tic-tac-toe")
async def tictactoe_command(interaction: discord.Interaction):
    board = [["1️⃣", "2️⃣", "3️⃣"], ["4️⃣", "5️⃣", "6️⃣"], ["7️⃣", "8️⃣", "9️⃣"]]
    display = "\n".join([" ".join(row) for row in board])
    embed = discord.Embed(title="⭕ Tic-Tac-Toe", description="React with a number to place your X!", color=0x3498DB)
    embed.add_field(name="Board", value=display, inline=False)
    embed.set_footer(text="Type a number (1-9) to make your move!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="connect4", description="Connect 4 info")
async def connect4_command(interaction: discord.Interaction):
    board = [["⚪" for _ in range(7)] for _ in range(6)]
    display = "\n".join([" ".join(row) for row in board])
    embed = discord.Embed(title="🔴 Connect 4", description="Drop your pieces to connect 4 in a row!", color=0xE74C3C)
    embed.add_field(name="Board", value=f"```{display}```", inline=False)
    embed.add_field(name="Columns", value="1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣", inline=False)
    embed.set_footer(text="Type a column number (1-7) to drop your piece!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="battleship", description="Battleship game start")
async def battleship_command(interaction: discord.Interaction):
    grid = [["🌊" for _ in range(5)] for _ in range(5)]
    ship_row = random.randint(0, 4)
    ship_col = random.randint(0, 4)
    display = "\n".join([" ".join(row) for row in grid])
    embed = discord.Embed(title="🚢 Battleship", description="Find the hidden ship!", color=0x3498DB)
    embed.add_field(name="Ocean", value=f"```{display}```", inline=False)
    embed.add_field(name="How to Play", value="Guess coordinates like `A1`, `B3`, etc.", inline=False)
    embed.set_footer(text=f"Ship location: ||Row {ship_row+1}, Col {ship_col+1}||")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="minesweeper", description="Minesweeper game")
async def minesweeper_command(interaction: discord.Interaction):
    grid_size = 5
    num_mines = 5
    grid = [[0 for _ in range(grid_size)] for _ in range(grid_size)]
    mines = random.sample(range(grid_size * grid_size), num_mines)
    for mine in mines:
        row, col = divmod(mine, grid_size)
        grid[row][col] = -1
    number_emojis = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
    display = []
    for row in range(grid_size):
        row_display = []
        for col in range(grid_size):
            if grid[row][col] == -1:
                row_display.append("||💣||")
            else:
                count = 0
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        nr, nc = row + dr, col + dc
                        if 0 <= nr < grid_size and 0 <= nc < grid_size and grid[nr][nc] == -1:
                            count += 1
                row_display.append(f"||{number_emojis[count]}||")
        display.append(" ".join(row_display))
    embed = discord.Embed(title="💣 Minesweeper", description="Click to reveal! Avoid the bombs!", color=0x7F8C8D)
    embed.add_field(name="Grid", value="\n".join(display), inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="simon", description="Simon Says memory game")
async def simon_command(interaction: discord.Interaction):
    colors = ["🔴", "🟢", "🔵", "🟡"]
    length = random.randint(4, 8)
    sequence = [random.choice(colors) for _ in range(length)]
    embed = discord.Embed(title="🔴🟢🔵🟡 Simon Says", description="Remember the sequence!", color=0x9B59B6)
    embed.add_field(name="Sequence", value=" ".join(sequence), inline=False)
    embed.set_footer(text="Memorize it! It will be hidden soon...")
    await interaction.response.send_message(embed=embed)
    await asyncio.sleep(4)
    embed2 = discord.Embed(title="🔴🟢🔵🟡 Simon Says", description="Now repeat the sequence!", color=0x9B59B6)
    embed2.add_field(name="Your Turn", value="Type the sequence using: R (red), G (green), B (blue), Y (yellow)", inline=False)
    embed2.set_footer(text=f"Answer: ||{' '.join(sequence)}||")
    await interaction.followup.send(embed=embed2)

@bot.tree.command(name="lottery", description="Try your luck in the lottery")
async def lottery_command(interaction: discord.Interaction):
    player_nums = sorted(random.sample(range(1, 50), 6))
    winning_nums = sorted(random.sample(range(1, 50), 6))
    matches = len(set(player_nums) & set(winning_nums))
    if matches == 6:
        result = "🎉 JACKPOT! You matched all 6!"
        color = 0xFFD700
    elif matches >= 4:
        result = f"🎊 Great! You matched {matches} numbers!"
        color = 0x00FF00
    elif matches >= 2:
        result = f"😊 You matched {matches} numbers!"
        color = 0xFFFF00
    else:
        result = f"😔 Only {matches} match(es). Better luck next time!"
        color = 0xFF0000
    embed = discord.Embed(title="🎱 Lottery Draw", color=color)
    embed.add_field(name="Your Numbers", value=" ".join(f"`{n}`" for n in player_nums), inline=False)
    embed.add_field(name="Winning Numbers", value=" ".join(f"`{n}`" for n in winning_nums), inline=False)
    embed.add_field(name="Result", value=result, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="blackjack2", description="Play blackjack")
async def blackjack2_command(interaction: discord.Interaction):
    cards = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
    suits = ["♠️", "♥️", "♦️", "♣️"]
    def get_card():
        return f"{random.choice(cards)}{random.choice(suits)}"
    def calc_hand(hand):
        total = 0
        aces = 0
        for card in hand:
            val = card[:-2]
            if val in ["J", "Q", "K"]:
                total += 10
            elif val == "A":
                total += 11
                aces += 1
            else:
                total += int(val)
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        return total
    player_hand = [get_card(), get_card()]
    dealer_hand = [get_card(), get_card()]
    player_total = calc_hand(player_hand)
    dealer_total = calc_hand(dealer_hand)
    while dealer_total < 17:
        dealer_hand.append(get_card())
        dealer_total = calc_hand(dealer_hand)
    if player_total == 21:
        result = "🎉 BLACKJACK! You win!"
        color = 0x00FF00
    elif player_total > 21:
        result = "💔 Bust! You lose."
        color = 0xFF0000
    elif dealer_total > 21:
        result = "🎉 Dealer busts! You win!"
        color = 0x00FF00
    elif player_total > dealer_total:
        result = "🎉 You win!"
        color = 0x00FF00
    elif dealer_total > player_total:
        result = "💔 Dealer wins."
        color = 0xFF0000
    else:
        result = "🤝 Push! It's a tie."
        color = 0xFFFF00
    embed = discord.Embed(title="🃏 Blackjack", color=color)
    embed.add_field(name="Your Hand", value=f"{' '.join(player_hand)} = **{player_total}**", inline=True)
    embed.add_field(name="Dealer's Hand", value=f"{' '.join(dealer_hand)} = **{dealer_total}**", inline=True)
    embed.add_field(name="Result", value=result, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="wheel", description="Spin the wheel of fortune")
async def wheel_command(interaction: discord.Interaction):
    prizes = ["🎁 Mystery Box", "💰 100 Coins", "⭐ 50 XP", "🍀 Lucky Charm", "💎 Rare Gem", "🎟️ Bonus Ticket", "🌟 Super Star", "💫 Cosmic Dust", "🔮 Magic Orb", "🏆 Grand Prize"]
    weights = [10, 20, 20, 15, 5, 15, 5, 5, 3, 2]
    prize = random.choices(prizes, weights=weights)[0]
    embed = discord.Embed(title="🎡 Wheel of Fortune", color=0xF1C40F)
    embed.add_field(name="Spinning...", value="🎡 ➜ 🎡 ➜ 🎡", inline=False)
    msg = await interaction.response.send_message(embed=embed)
    await asyncio.sleep(2)
    embed2 = discord.Embed(title="🎡 Wheel of Fortune", color=0x00FF00)
    embed2.add_field(name="You Won!", value=f"**{prize}**", inline=False)
    await interaction.edit_original_response(embed=embed2)

@bot.tree.command(name="duel", description="Challenge someone to a duel")
@app_commands.describe(opponent="Who to duel")
async def duel_command(interaction: discord.Interaction, opponent: discord.Member):
    if opponent.id == interaction.user.id:
        await interaction.response.send_message("You can't duel yourself!", ephemeral=True)
        return
    player_hp = 100
    opp_hp = 100
    turns = []
    while player_hp > 0 and opp_hp > 0:
        p_dmg = random.randint(5, 25)
        o_dmg = random.randint(5, 25)
        opp_hp -= p_dmg
        player_hp -= o_dmg
        turns.append(f"⚔️ You dealt {p_dmg} | {opponent.display_name} dealt {o_dmg}")
    winner = interaction.user if opp_hp <= 0 else opponent
    embed = discord.Embed(title="⚔️ Duel Results", color=0xE74C3C)
    embed.add_field(name="Battle Log", value="\n".join(turns[-3:]), inline=False)
    embed.add_field(name="Winner", value=f"🏆 **{winner.display_name}**", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="games", description="View all available games")
async def games_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🎮 All Games", description="Here are all the games you can play!", color=0x9B59B6)
    embed.add_field(name="🧠 Trivia & Puzzles", value="`/trivia` `/riddle` `/mathquiz` `/pattern` `/scramble` `/hangman` `/emoji`", inline=False)
    embed.add_field(name="🎲 Luck Games", value="`/roll` `/flip` `/8ball` `/fortune` `/horoscope` `/lottery` `/wheel`", inline=False)
    embed.add_field(name="🎰 Casino", value="`/slots2` `/blackjack2` `/rps`", inline=False)
    embed.add_field(name="🧩 Memory & Skills", value="`/memory` `/reaction` `/simon` `/typingrace` `/guess`", inline=False)
    embed.add_field(name="👥 Social Games", value="`/wouldyourather` `/neverhaveiever` `/truthordare` `/ship` `/fight` `/duel`", inline=False)
    embed.add_field(name="📝 Word Games", value="`/wordchain` `/categories` `/acronym` `/storytime`", inline=False)
    embed.add_field(name="🎯 Classic Games", value="`/tictactoe` `/connect4` `/battleship` `/minesweeper`", inline=False)
    embed.add_field(name="😂 Fun", value="`/joke` `/dadjoke` `/fact` `/quote` `/pickup` `/roast` `/compliment` `/rate`", inline=False)
    await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="puppytraining", description="Secret puppy training session")
    async def puppy_training_command(interaction: discord.Interaction):
        user_id = interaction.user.id
        channel_id = interaction.channel.id
        
        if user_id in puppy_training_sessions:
            await interaction.response.send_message("You already have an active puppy training session! Use `/stoppuppytraining` to stop it.", ephemeral=True)
            return

        # Request password
        await interaction.response.send_message("🐶 To start the secret training, please type the password in the chat.", ephemeral=True)

        def check(m):
            return m.author.id == user_id and m.channel.id == channel_id and m.content == "Iampuppy"

        try:
            msg = await bot.wait_for('message', check=check, timeout=60.0)
            # Delete the password message for security if bot has permissions
            try:
                await msg.delete()
            except:
                pass
        except asyncio.TimeoutError:
            await interaction.followup.send("⌛ Password entry timed out. Please try the command again.", ephemeral=True)
            return

        puppy_training_sessions[user_id] = {"channel_id": channel_id, "active": True, "count": 0}
        embed = discord.Embed(title="🐶 Puppy Training Started", description="Good puppy! Password accepted. Training has begun...", color=0xFF69B4)
        await interaction.followup.send(embed=embed)
        
        async def training_loop():
            max_repeats = 50
            delay = 3
            while user_id in puppy_training_sessions and puppy_training_sessions[user_id]["active"]:
                puppy_training_sessions[user_id]["count"] += 1
                count = puppy_training_sessions[user_id]["count"]
                if count > max_repeats:
                    del puppy_training_sessions[user_id]
                    try:
                        channel = bot.get_channel(channel_id)
                        if channel:
                            await channel.send("🐶 Training session complete! You did great, good puppy!")
                    except:
                        pass
                    break
                try:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        await channel.send(f"🐶 Yes you are a good puppy! Repeat, \"I am a good Puppy\" and **Finish**")
                except:
                    break
                await asyncio.sleep(delay)
        asyncio.create_task(training_loop())

@bot.tree.command(name="stoppuppytraining", description="Stop the puppy training session")
async def stop_puppy_training_command(interaction: discord.Interaction):
    user_id = interaction.user.id
    if user_id not in puppy_training_sessions:
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        if is_admin:
            for uid in list(puppy_training_sessions.keys()):
                if puppy_training_sessions[uid].get("channel_id") == interaction.channel.id:
                    del puppy_training_sessions[uid]
                    await interaction.response.send_message("🛑 Admin stopped the puppy training session in this channel.", ephemeral=False)
                    return
        await interaction.response.send_message("You don't have an active puppy training session!", ephemeral=True)
        return
    del puppy_training_sessions[user_id]
    embed = discord.Embed(title="🛑 Puppy Training Stopped", description="Good job! Training session has ended. You're such a good puppy!", color=0x00FF00)
    await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="intro", description="Everything you need to know about the Ultimate Bot")
    async def intro_command(interaction: discord.Interaction):
        embed = discord.Embed(
            title="✨ Welcome to Ultimate Bot! ✨",
            description="Your all-in-one companion for gaming, music, and AI chat!",
            color=discord.Color.gold()
        )
        embed.add_field(name="🎣 Fishing", value="Travel biomes, upgrade gear, and catch mythic creatures!", inline=False)
        embed.add_field(name="🚜 Farming", value="Plant crops, wait for growth, and harvest for huge profits!", inline=False)
        embed.add_field(name="🏹 Hunting & Relics", value="Hunt animals in dangerous areas and find ancient relics to boost stats!", inline=False)
        embed.add_field(name="🏰 Dungeons & PvP", value="Fight through dungeons to rank up and battle other players!", inline=False)
        embed.add_field(name="🎰 Casino", value="Try your luck at Slots, Blackjack, Roulette, and more!", inline=False)
        embed.add_field(name="🎵 Music", value="High-quality audio streaming with a powerful queue system!", inline=False)
        embed.add_field(name="🤖 AI Chat", value="Intelligent AI that remembers you and learns your personality!", inline=False)
        
        embed.set_footer(text="Use /help to see all commands!")
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="farm", description="Manage your virtual farm")
async def farm_command(interaction: discord.Interaction):
    await show_farm_menu(interaction)

@bot.tree.command(name="plant", description="Plant a crop in your farm")
@app_commands.describe(crop="The crop you want to plant")
async def plant_command(interaction: discord.Interaction, crop: str):
    crop = crop.lower()
    if crop not in CROPS:
        await interaction.response.send_message(f"That's not a valid crop! Available: {', '.join(CROPS.keys())}", ephemeral=True)
        return
        
    user_id = interaction.user.id
    player_data = await get_or_create_player(user_id)
    if player_data["level"] < CROPS[crop]["min_level"]:
        await interaction.response.send_message(f"You need to be level {CROPS[crop]['min_level']} to plant {crop}!", ephemeral=True)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM farm WHERE user_id = ?", (user_id,))
        count = (await cur.fetchone())[0]
        if count >= 5: # Limit to 5 plots
            await interaction.response.send_message("You've run out of space on your farm! Harvest some crops first.", ephemeral=True)
            return
        
        await db.execute("INSERT INTO farm (user_id, plot_id, crop_type, plant_time) VALUES (?, ?, ?, ?)",
                       (user_id, count + 1, crop, time.time()))
        await db.commit()
        
    await interaction.response.send_message(f"🌱 You planted {CROPS[crop]['emoji']} **{crop.title()}** in Plot {count + 1}!")
    await show_farm_menu(interaction)

@bot.tree.command(name="harvest", description="Harvest all ready crops")
async def harvest_command(interaction: discord.Interaction):
    await harvest_crops(interaction)

async def show_areas_embed(interaction: discord.Interaction):
    embed = discord.Embed(title="🏹 Hunting Areas", color=discord.Color.green())
    for area, data in HUNTING_AREAS.items():
        mobs = ", ".join(data["mobs"])
        embed.add_field(
            name=f"{area.title()} (Lvl {data['min_level']}+)",
            value=f"**Mobs:** {mobs}\n**Relic Chance:** {data['relic_chance']*100}%",
            inline=False
        )
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="areas", description="View all available hunting areas")
async def areas_command(interaction: discord.Interaction):
    await show_areas_embed(interaction)

@bot.tree.command(name="hunt", description="Go hunting for animals and relics")
@app_commands.describe(area="Where to hunt")
async def hunt_command(interaction: discord.Interaction, area: str):
    await interaction.response.defer()
    await do_hunting(interaction, area=area)

@bot.tree.command(name="dungeon", description="Enter a dungeon to fight and rank up")
@app_commands.describe(dungeon="Which dungeon to enter")
async def dungeon_command(interaction: discord.Interaction, dungeon: str):
    await interaction.response.defer()
    await do_dungeon(interaction, dungeon=dungeon)

@bot.tree.command(name="leaderboards", description="See who is the #1 in the world")
async def leaderboards_command(interaction: discord.Interaction):
    # Simple top coins leaderboard for now
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id, coins, level FROM players ORDER BY coins DESC LIMIT 5")
        rows = await cur.fetchall()
        
        embed = discord.Embed(title="🏆 Global Leaderboards", color=discord.Color.blue())
        lb_text = ""
        for i, row in enumerate(rows, 1):
            name = f"User {row[0]}" # Simplified for now
            lb_text += f"{i}. **{name}** - Lvl {row[2]} | {row[1]} coins\n"
        
        embed.add_field(name="💰 Wealthiest Players", value=lb_text or "No data yet!", inline=False)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="sync", description="Admin only: Force sync slash commands")
@app_commands.checks.has_permissions(administrator=True)
async def sync_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        synced = await bot.tree.sync()
        await interaction.followup.send(f"✅ Successfully synced {len(synced)} commands globally!")
    except discord.HTTPException as e:
        if e.status == 429:
            await interaction.followup.send("❌ Discord is rate-limiting this action. Please try again in 10-15 minutes.")
        else:
            await interaction.followup.send(f"❌ Failed to sync: {e}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}")

@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 Bot Commands", description="Here are all available commands!", color=0x00AAFF)
    
    embed.add_field(name="🏠 General", value="`/home` - Main menu\n`/profile` - Your profile\n`/tutorials` - Learn the bot\n`/help` - This menu", inline=True)
    embed.add_field(name="🎣 Fishing", value="`/fish` - Go fishing\n`/inventory` - Fish collection\n`/sell` - Sell fish\n`/biomes` - View biomes\n`/pets` - Pet collection\n`/chests` - Treasure chests\n`/openchest` - Open chests", inline=True)
    embed.add_field(name="💰 Economy", value="`/shop` - Buy upgrades\n`/work` - Do a job\n`/leaderboard` - Rankings", inline=True)
    embed.add_field(name="🎰 Casino", value="`/casino` - Casino menu\n`/slots` - Slot machine\n`/coinflip` - Flip a coin", inline=True)
    embed.add_field(name="🎵 Music", value="`/play` - Play music\n`/skip` - Skip song\n`/stop` - Stop & leave\n`/pause` - Pause\n`/resume` - Resume\n`/queue` - View queue\n`/nowplaying` - Current song", inline=True)
    embed.add_field(name="🤖 AI & Settings", value="`/talk` - Chat with AI\n`/reset` - Reset data", inline=True)
    embed.add_field(name="🎮 40+ Games", value="`/games` - View all games!", inline=False)
    
    await interaction.response.send_message(embed=embed)

if __name__ == "__main__":
    if not TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN not found!")
        print("Please add your Discord bot token to the Secrets.")
        print("\nSteps:")
        print("1. Go to https://discord.com/developers/applications")
        print("2. Select your application > Bot")
        print("3. Copy the bot token")
        print("4. Add it to Secrets as DISCORD_BOT_TOKEN")
    else:
        try:
            @bot.event
            async def on_ready():
                print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
                
                # Copy global commands to each guild and sync - THIS BYPASSES GLOBAL SYNC DELAYS
                for guild in bot.guilds:
                    try:
                        bot.tree.copy_global_to(guild=guild)
                        await bot.tree.sync(guild=guild)
                        print(f"✅ Immediate sync: {len(bot.tree.get_commands(guild=guild))} commands for guild: {guild.name}")
                    except Exception as e:
                        print(f"❌ Failed to sync for {guild.name}: {e}")
                
                try:
                    # One last attempt at global sync
                    print("⏳ Final global sync attempt...")
                    synced = await bot.tree.sync()
                    print(f"✅ Global sync successful! ({len(synced)} commands)")
                except discord.HTTPException as e:
                    if e.status == 429:
                        print("ℹ️ Global sync still pending (Rate limit). Guild-level sync is active!")
                    else:
                        print(f"❌ Global sync failed: {e}")

            bot.run(TOKEN)
        except discord.LoginFailure:
            print("❌ Invalid bot token. Please check DISCORD_BOT_TOKEN.")
        except discord.PrivilegedIntentsRequired:
            print("❌ Enable SERVER MEMBERS and MESSAGE CONTENT intents in Developer Portal.")
        except Exception as e:
            print(f"❌ Error: {e}")
