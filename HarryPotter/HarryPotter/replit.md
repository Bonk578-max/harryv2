# Ultimate Discord Bot

## Overview
A feature-rich Discord bot built in Python featuring multiple game systems (fishing, casino, jobs), music playback, AI chat with memory, and moderation tools. The bot uses Discord.py with slash commands, SQLite for data persistence, and provides an interactive UI with embeds and buttons.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### Core Framework
- **Discord.py with app_commands**: Modern Discord bot using slash commands and interactive components (buttons, embeds)
- **Single-file architecture**: Main bot logic contained in `main.py` for simplicity
- **Async/await pattern**: Fully asynchronous design using Python's asyncio for non-blocking operations

### Data Storage
- **SQLite with aiosqlite**: Async SQLite databases for persistent storage
  - `guild_config.db`: Server-specific settings (welcome channels, mod logs, auto-roles)
  - `fishing_game.db`: Player data, inventories, progression, and game state
- **JSON serialization**: Complex data structures (inventories, equipped items) stored as JSON in database columns

### Game Systems Architecture
- **Fishing System**: 12+ biomes with level-locking, 6 fish rarities, equipment upgrades (rods/boats), pet collection, charm system, and prestige mechanics
- **Casino Games**: Slots, blackjack, roulette, dice, coinflip with virtual currency
- **Jobs System**: 6 job types unlocked by level with cooldown-based earnings
- **Progression**: XP/leveling system with level^1.5 scaling, coins as currency

### Interactive UI Pattern
- **Embed-based displays**: Rich embeds for all game interfaces and information
- **Button navigation**: Discord UI components for user interaction instead of text commands
- **View classes**: Discord.py View subclasses manage button states and callbacks

### Optional Integrations
- **OpenAI API**: AI chat functionality with conversation memory (requires API key)
- **yt-dlp**: YouTube/music playback support (optional dependency)

## External Dependencies

### Required
- **discord.py**: Discord API wrapper with slash command support
- **aiosqlite**: Async SQLite database access
- **python-dotenv**: Environment variable management for secrets
- **pynacl**: Required for voice support
- **ffmpeg**: System dependency for audio playback

### Optional
- **openai**: OpenAI API client for AI chat features (enabled if `OPENAI_API_KEY` provided)
- **yt-dlp**: YouTube audio extraction for music player functionality
- **spotipy**: Spotify integration

### Environment Variables (Secrets)
- `DISCORD_BOT_TOKEN`: Required - Discord bot authentication token
- `OPENAI_API_KEY`: Optional - Enables AI chat features

### Database Files (Auto-created)
- `guild_config.db`: Guild-specific configuration
- `fishing_game.db`: Game progression and player data

## Running the Bot
The bot runs with: `python main.py`

The bot requires a valid Discord bot token set as the `DISCORD_BOT_TOKEN` secret.
