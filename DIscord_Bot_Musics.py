import asyncio
import os
import random
from collections import deque
from pathlib import Path

import discord
from discord.ext import commands
import yt_dlp
from dotenv import load_dotenv


env_path = Path(__file__).parent / "DISCORD_TOKEN_2.env"
load_dotenv(dotenv_path=env_path)

TOKEN = os.getenv("DISCORD_TOKEN_2")

if not TOKEN:
    raise ValueError("Токен не найден в DISCORD_TOKEN_2.env")


intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="Kuno",
    intents=intents,
    case_insensitive=True
)


queues = {}
current_song = {}


YDL_BASE_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "ignoreerrors": False,
    "no_warnings": False,
    "default_search": "auto",

    "retries": 5,
    "fragment_retries": 5,
    "extractor_retries": 3,

    "socket_timeout": 30,

    "geo_bypass": True,

    "prefer_ffmpeg": True,

    "js_runtimes": {
        "deno": {}
    },

    "extractor_args": {
        "youtube": {
            "player_client": [
                "default",
                "-android_vr"
            ]
        }
    },

    "quiet": False,
}


FFMPEG_OPTIONS = {
    "before_options": (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5 "
        "-rw_timeout 15000000"
    ),
    "options": "-vn -filter:a \"volume=0.5\"",
}


def create_yt_options(use_cookies=False):
    options = dict(YDL_BASE_OPTIONS)

    options["extractor_args"] = {
        "youtube": {
            "player_client": [
                "default",
                "-android_vr"
            ]
        }
    }

    options["js_runtimes"] = {
        "deno": {}
    }

    if use_cookies:
        options["cookiesfrombrowser"] = (
            "firefox",
        )

    return options


def is_age_restriction_error(error):
    text = str(error).lower()

    age_errors = [
        "sign in to confirm your age",
        "confirm your age",
        "this video may be inappropriate",
        "age-restricted",
        "age restricted",
        "inappropriate for some users",
        "use --cookies-from-browser",
    ]

    return any(
        phrase in text
        for phrase in age_errors
    )


def get_video_info(url):
    first_error = None

    try:
        print(
            "[yt-dlp] Попытка получения видео "
            "без cookies..."
        )

        options = create_yt_options(
            use_cookies=False
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                url,
                download=False
            )

        if not info:
            raise Exception(
                "YouTube не вернул информацию о видео"
            )

        print(
            "[yt-dlp] Видео получено "
            "без cookies"
        )

        return info

    except Exception as error:
        first_error = error

        print(
            f"[yt-dlp] Первая попытка не удалась: "
            f"{error}"
        )

        if not is_age_restriction_error(error):
            raise

    print(
        "[yt-dlp] Обнаружено ограничение по возрасту."
    )

    print(
        "[yt-dlp] Повторная попытка "
        "с cookies Firefox..."
    )

    try:
        options = create_yt_options(
            use_cookies=True
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                url,
                download=False
            )

        if not info:
            raise Exception(
                "YouTube не вернул информацию "
                "при использовании cookies"
            )

        print(
            "[yt-dlp] Видео успешно получено "
            "с cookies Firefox"
        )

        return info

    except Exception as second_error:
        print(
            "[yt-dlp] Не удалось получить видео "
            "с cookies Firefox:"
        )

        print(
            f"[yt-dlp] {second_error}"
        )

        raise Exception(
            "YouTube требует подтверждение возраста, "
            "но не удалось использовать cookies Firefox. "
            "Убедитесь, что вы вошли в YouTube через Firefox "
            "и полностью закройте Firefox перед запуском бота."
        ) from second_error


def get_fresh_audio_url(url):
    first_error = None

    try:
        print(
            "[yt-dlp] Получение свежего аудио URL "
            "без cookies..."
        )

        options = create_yt_options(
            use_cookies=False
        )

        options["format"] = (
            "bestaudio[acodec!=none]/best"
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                url,
                download=False
            )

        if not info:
            raise Exception(
                "YouTube не вернул информацию о видео"
            )

        audio_url = extract_audio_url(
            info
        )

        print(
            "[yt-dlp] Аудио URL получен "
            "без cookies"
        )

        return audio_url

    except Exception as error:
        first_error = error

        print(
            f"[yt-dlp] Ошибка первой попытки "
            f"получения аудио: {error}"
        )

        if not is_age_restriction_error(error):
            raise

    print(
        "[yt-dlp] Требуются cookies Firefox."
    )

    try:
        print(
            "[yt-dlp] Повторное получение аудио "
            "с cookies Firefox..."
        )

        options = create_yt_options(
            use_cookies=True
        )

        options["format"] = (
            "bestaudio[acodec!=none]/best"
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(
                url,
                download=False
            )

        if not info:
            raise Exception(
                "YouTube не вернул информацию "
                "при использовании cookies"
            )

        audio_url = extract_audio_url(
            info
        )

        print(
            "[yt-dlp] Аудио URL получен "
            "с cookies Firefox"
        )

        return audio_url

    except Exception as second_error:
        print(
            "[yt-dlp] Не удалось получить аудио "
            "с cookies Firefox:"
        )

        print(
            f"[yt-dlp] {second_error}"
        )

        raise Exception(
            "Не удалось получить аудиопоток YouTube. "
            "Если видео имеет ограничение 18+, "
            "убедитесь, что вы вошли в YouTube через Firefox "
            "и полностью закрыли Firefox перед запуском бота."
        ) from second_error


def extract_audio_url(info):
    audio_url = info.get("url")

    if audio_url:
        return audio_url

    formats = info.get(
        "formats",
        []
    )

    audio_formats = [
        fmt
        for fmt in formats
        if (
            fmt.get("url")
            and fmt.get("acodec")
            and fmt.get("acodec") != "none"
        )
    ]

    if not audio_formats:
        raise Exception(
            "YouTube не предоставил доступный аудиопоток"
        )

    audio_formats.sort(
        key=lambda fmt: (
            fmt.get("abr") or 0,
            fmt.get("tbr") or 0
        ),
        reverse=True
    )

    return audio_formats[0]["url"]


async def get_info_async(url):
    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(
        None,
        lambda: get_video_info(url)
    )



async def get_audio_url_async(url):
    loop = asyncio.get_running_loop()

    return await loop.run_in_executor(
        None,
        lambda: get_fresh_audio_url(url)
    )


async def add_songs_from_query(
    query,
    requester
):
    data = await get_info_async(
        query
    )

    songs = []

    if "entries" in data:
        for entry in data["entries"]:
            if entry:
                songs.append(
                    Song(
                        entry,
                        requester
                    )
                )
    else:
        songs.append(
            Song(
                data,
                requester
            )
        )

    return songs


class Song:
    def __init__(
        self,
        data,
        requester
    ):
        self.title = data.get(
            "title",
            "Неизвестное название"
        )

        self.webpage_url = (
            data.get("webpage_url")
            or data.get("original_url")
            or ""
        )

        self.audio_url = None

        self.duration = data.get(
            "duration",
            0
        )

        self.thumbnail = data.get(
            "thumbnail"
        )

        self.requester = requester

        self.data = data

    def get_embed(self):
        embed = discord.Embed(
            title="Сейчас играет",
            description=(
                f"[{self.title}]"
                f"({self.webpage_url})"
            ),
            color=discord.Color.blue()
        )

        if self.thumbnail:
            embed.set_thumbnail(
                url=self.thumbnail
            )

        if self.duration:
            mins, secs = divmod(
                int(self.duration),
                60
            )

            embed.add_field(
                name="Длительность",
                value=f"{mins}:{secs:02d}"
            )

        embed.add_field(
            name="Добавил",
            value=self.requester.mention
        )

        embed.set_footer(
            text="Музыкальный бот"
        )

        return embed


async def play_next(
    guild,
    text_channel
):
    guild_id = guild.id

    voice_client = guild.voice_client

    if (
        not voice_client
        or not voice_client.is_connected()
    ):
        current_song.pop(
            guild_id,
            None
        )
        return

    if (
        guild_id not in queues
        or not queues[guild_id]
    ):
        current_song.pop(
            guild_id,
            None
        )
        return

    song = queues[guild_id].popleft()

    current_song[guild_id] = song

    try:
        print(
            f"[DEBUG] Получение свежего "
            f"аудио URL: {song.title}"
        )

        song.audio_url = await get_audio_url_async(
            song.webpage_url
        )

        if not song.audio_url:
            raise Exception(
                "Не удалось получить прямую ссылку "
                "на аудио"
            )

        source = discord.FFmpegPCMAudio(
            song.audio_url,
            **FFMPEG_OPTIONS
        )

        def after_playing(error):
            if error:
                print(
                    f"[FFmpeg] Ошибка "
                    f"воспроизведения: {error}"
                )

            future = asyncio.run_coroutine_threadsafe(
                play_next(
                    guild,
                    text_channel
                ),
                bot.loop
            )

            try:
                future.result()
            except Exception as callback_error:
                print(
                    f"[DEBUG] Ошибка play_next: "
                    f"{callback_error}"
                )

        voice_client.play(
            source,
            after=after_playing
        )

        await text_channel.send(
            embed=song.get_embed()
        )

        if (
            guild_id in queues
            and queues[guild_id]
        ):
            next_song = queues[guild_id][0]

            await text_channel.send(
                f"**Следующий:** "
                f"{next_song.title} "
                f"(добавил: "
                f"{next_song.requester.mention})"
            )

    except Exception as error:
        print(
            f"[ERROR] Не удалось воспроизвести "
            f"{song.title}: {error}"
        )

        current_song.pop(
            guild_id,
            None
        )

        try:
            await text_channel.send(
                f"Не удалось воспроизвести "
                f"**{song.title}**\n"
                f"Ошибка: `{error}`"
            )
        except Exception:
            pass

        await play_next(
            guild,
            text_channel
        )


async def disconnect_if_empty(guild):
    voice_client = guild.voice_client

    if not voice_client:
        return

    if len(voice_client.channel.members) > 1:
        return

    await asyncio.sleep(
        60
    )

    if (
        voice_client.is_connected()
        and len(voice_client.channel.members) == 1
    ):
        await voice_client.disconnect()

        queues.pop(
            guild.id,
            None
        )

        current_song.pop(
            guild.id,
            None
        )


class MusicCog(commands.Cog):
    def __init__(
        self,
        bot_instance
    ):
        self.bot = bot_instance

    @commands.command(
        name="play"
    )
    async def play_command(
        self,
        ctx,
        *,
        query
    ):
        if not ctx.author.voice:
            await ctx.send(
                "Вы должны быть в голосовом канале!"
            )
            return

        voice_channel = (
            ctx.author.voice.channel
        )

        if not ctx.voice_client:
            await voice_channel.connect()

        elif (
            ctx.voice_client.channel
            != voice_channel
        ):
            await ctx.voice_client.move_to(
                voice_channel
            )

        async with ctx.typing():
            try:
                songs = await add_songs_from_query(
                    query,
                    ctx.author
                )

                if not songs:
                    await ctx.send(
                        "Не удалось найти треки."
                    )
                    return

                guild_id = ctx.guild.id

                if guild_id not in queues:
                    queues[guild_id] = deque()

                for song in songs:
                    queues[guild_id].append(
                        song
                    )

                await ctx.send(
                    f"Добавлено треков: "
                    f"**{len(songs)}**"
                )

                if (
                    not ctx.voice_client.is_playing()
                    and not ctx.voice_client.is_paused()
                ):
                    await play_next(
                        ctx.guild,
                        ctx.channel
                    )

            except Exception as error:
                await ctx.send(
                    f"Ошибка при обработке запроса:\n"
                    f"`{error}`"
                )

                print(
                    f"[DEBUG] Ошибка команды play: "
                    f"{error}"
                )

    @commands.command(
        name="queue"
    )
    async def queue_command(
        self,
        ctx
    ):
        guild_id = ctx.guild.id

        if (
            guild_id not in queues
            or not queues[guild_id]
        ):
            await ctx.send(
                "Очередь пуста."
            )
            return

        embed = discord.Embed(
            title="Очередь воспроизведения",
            color=discord.Color.green()
        )

        if guild_id in current_song:
            song = current_song[guild_id]

            embed.add_field(
                name="Сейчас играет",
                value=(
                    f"**{song.title}**\n"
                    f"(добавил: "
                    f"{song.requester.mention})"
                ),
                inline=False
            )

        queue_list = list(
            queues[guild_id]
        )

        text = ""

        for index, song in enumerate(
            queue_list[:10],
            1
        ):
            if song.duration:
                duration = (
                    f"{song.duration // 60}:"
                    f"{song.duration % 60:02d}"
                )
            else:
                duration = "?:??"

            text += (
                f"**{index}.** "
                f"{song.title} "
                f"({duration}) - "
                f"{song.requester.mention}\n"
            )

        if len(queue_list) > 10:
            text += (
                f"\n...и еще "
                f"{len(queue_list) - 10} треков"
            )

        if text:
            embed.add_field(
                name="Очередь",
                value=text,
                inline=False
            )

        await ctx.send(
            embed=embed
        )

    @commands.command(
        name="skip"
    )
    async def skip_command(
        self,
        ctx
    ):
        if (
            not ctx.voice_client
            or not ctx.voice_client.is_connected()
        ):
            await ctx.send(
                "Я не подключен "
                "к голосовому каналу."
            )
            return

        if not ctx.voice_client.is_playing():
            await ctx.send(
                "Сейчас ничего не играет."
            )
            return

        ctx.voice_client.stop()

        await ctx.send(
            "Трек пропущен."
        )

    @commands.command(
        name="stop"
    )
    async def stop_command(
        self,
        ctx
    ):
        if not ctx.voice_client:
            await ctx.send(
                "Бот не подключен "
                "к голосовому каналу."
            )
            return

        ctx.voice_client.stop()

        guild_id = ctx.guild.id

        queues.pop(
            guild_id,
            None
        )

        current_song.pop(
            guild_id,
            None
        )

        await ctx.voice_client.disconnect()

        await ctx.send(
            "Музыка остановлена, "
            "очередь очищена."
        )

    @commands.command(
        name="pause"
    )
    async def pause_command(
        self,
        ctx
    ):
        if (
            ctx.voice_client
            and ctx.voice_client.is_playing()
        ):
            ctx.voice_client.pause()

            await ctx.send(
                "Музыка приостановлена."
            )
        else:
            await ctx.send(
                "Сейчас ничего не играет."
            )

    @commands.command(
        name="resume"
    )
    async def resume_command(
        self,
        ctx
    ):
        if (
            ctx.voice_client
            and ctx.voice_client.is_paused()
        ):
            ctx.voice_client.resume()

            await ctx.send(
                "Музыка возобновлена."
            )
        else:
            await ctx.send(
                "Музыка не находится на паузе."
            )

    @commands.command(
        name="remove"
    )
    async def remove_command(
        self,
        ctx,
        index: int
    ):
        guild_id = ctx.guild.id

        if (
            guild_id not in queues
            or not queues[guild_id]
        ):
            await ctx.send(
                "Очередь пуста."
            )
            return

        if (
            index < 1
            or index > len(queues[guild_id])
        ):
            await ctx.send(
                f"Неверный номер. "
                f"Введите число от 1 до "
                f"{len(queues[guild_id])}"
            )
            return

        queue_list = list(
            queues[guild_id]
        )

        removed = queue_list.pop(
            index - 1
        )

        queues[guild_id] = deque(
            queue_list
        )

        await ctx.send(
            f"Удален трек: "
            f"**{removed.title}**"
        )

    @commands.command(
        name="clear"
    )
    async def clear_command(
        self,
        ctx
    ):
        guild_id = ctx.guild.id

        if guild_id in queues:
            queues[guild_id].clear()

        await ctx.send(
            "Очередь очищена."
        )

    @commands.command(
        name="nowplaying"
    )
    async def nowplaying_command(
        self,
        ctx
    ):
        guild_id = ctx.guild.id

        if (
            guild_id in current_song
            and current_song[guild_id]
        ):
            await ctx.send(
                embed=current_song[guild_id].get_embed()
            )
        else:
            await ctx.send(
                "Сейчас ничего не играет."
            )

    @commands.command(
        name="shuffle"
    )
    async def shuffle_command(
        self,
        ctx
    ):
        guild_id = ctx.guild.id

        if (
            guild_id not in queues
            or len(queues[guild_id]) < 2
        ):
            await ctx.send(
                "В очереди недостаточно треков "
                "для перемешивания."
            )
            return

        queue_list = list(
            queues[guild_id]
        )

        random.shuffle(
            queue_list
        )

        queues[guild_id] = deque(
            queue_list
        )

        await ctx.send(
            "Очередь перемешана."
        )

    @commands.command(
        name="leave"
    )
    async def leave_command(
        self,
        ctx
    ):
        guild_id = ctx.guild.id

        if not ctx.voice_client:
            await ctx.send(
                "Я не подключен "
                "к голосовому каналу."
            )
            return

        queues.pop(
            guild_id,
            None
        )

        current_song.pop(
            guild_id,
            None
        )

        await ctx.voice_client.disconnect()

        await ctx.send(
            "Отключился от голосового канала."
        )


class SlashCog(commands.Cog):
    def __init__(
        self,
        bot_instance
    ):
        self.bot = bot_instance

    @discord.app_commands.command(
        name="play",
        description="Воспроизвести музыку из YouTube"
    )
    @discord.app_commands.describe(
        query="Ссылка на YouTube или название трека"
    )
    async def play_slash(
        self,
        interaction,
        query: str
    ):
        await interaction.response.defer(
            thinking=True
        )

        if not interaction.user.voice:
            await interaction.followup.send(
                "Вы должны быть в голосовом канале!",
                ephemeral=True
            )
            return

        guild = interaction.guild

        if guild is None:
            await interaction.followup.send(
                "Команда доступна только на сервере.",
                ephemeral=True
            )
            return

        voice_channel = (
            interaction.user.voice.channel
        )

        if not guild.voice_client:
            await voice_channel.connect()

        elif (
            guild.voice_client.channel
            != voice_channel
        ):
            await guild.voice_client.move_to(
                voice_channel
            )

        try:
            songs = await add_songs_from_query(
                query,
                interaction.user
            )

            if not songs:
                await interaction.followup.send(
                    "Не удалось найти треки.",
                    ephemeral=True
                )
                return

            guild_id = guild.id

            if guild_id not in queues:
                queues[guild_id] = deque()

            for song in songs:
                queues[guild_id].append(
                    song
                )

            await interaction.followup.send(
                f"Добавлено треков: "
                f"**{len(songs)}**"
            )

            if (
                not guild.voice_client.is_playing()
                and not guild.voice_client.is_paused()
            ):
                await play_next(
                    guild,
                    interaction.channel
                )

        except Exception as error:
            print(
                f"[DEBUG] Ошибка slash play: "
                f"{error}"
            )

            await interaction.followup.send(
                f"Ошибка:\n`{error}`",
                ephemeral=True
            )

    @discord.app_commands.command(
        name="queue",
        description="Показать текущую очередь"
    )
    async def queue_slash(
        self,
        interaction
    ):
        guild_id = interaction.guild.id

        if (
            guild_id not in queues
            or not queues[guild_id]
        ):
            await interaction.response.send_message(
                "Очередь пуста.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Очередь воспроизведения",
            color=discord.Color.green()
        )

        if guild_id in current_song:
            song = current_song[guild_id]

            embed.add_field(
                name="Сейчас играет",
                value=(
                    f"**{song.title}**\n"
                    f"(добавил: "
                    f"{song.requester.mention})"
                ),
                inline=False
            )

        queue_list = list(
            queues[guild_id]
        )

        text = ""

        for index, song in enumerate(
            queue_list[:10],
            1
        ):
            if song.duration:
                duration = (
                    f"{song.duration // 60}:"
                    f"{song.duration % 60:02d}"
                )
            else:
                duration = "?:??"

            text += (
                f"**{index}.** "
                f"{song.title} "
                f"({duration}) - "
                f"{song.requester.mention}\n"
            )

        if len(queue_list) > 10:
            text += (
                f"\n...и еще "
                f"{len(queue_list) - 10} треков"
            )

        if text:
            embed.add_field(
                name="Очередь",
                value=text,
                inline=False
            )

        await interaction.response.send_message(
            embed=embed
        )

    @discord.app_commands.command(
        name="skip",
        description="Пропустить текущий трек"
    )
    async def skip_slash(
        self,
        interaction
    ):
        voice_client = (
            interaction.guild.voice_client
        )

        if (
            not voice_client
            or not voice_client.is_connected()
        ):
            await interaction.response.send_message(
                "Я не подключен "
                "к голосовому каналу.",
                ephemeral=True
            )
            return

        if not voice_client.is_playing():
            await interaction.response.send_message(
                "Сейчас ничего не играет.",
                ephemeral=True
            )
            return

        voice_client.stop()

        await interaction.response.send_message(
            "Трек пропущен."
        )

    @discord.app_commands.command(
        name="pause",
        description="Приостановить воспроизведение"
    )
    async def pause_slash(
        self,
        interaction
    ):
        voice_client = (
            interaction.guild.voice_client
        )

        if (
            voice_client
            and voice_client.is_playing()
        ):
            voice_client.pause()

            await interaction.response.send_message(
                "Музыка приостановлена."
            )
        else:
            await interaction.response.send_message(
                "Сейчас ничего не играет.",
                ephemeral=True
            )

    @discord.app_commands.command(
        name="resume",
        description="Возобновить музыку"
    )
    async def resume_slash(
        self,
        interaction
    ):
        voice_client = (
            interaction.guild.voice_client
        )

        if (
            voice_client
            and voice_client.is_paused()
        ):
            voice_client.resume()

            await interaction.response.send_message(
                "Музыка возобновлена."
            )
        else:
            await interaction.response.send_message(
                "Музыка не находится на паузе.",
                ephemeral=True
            )

    @discord.app_commands.command(
        name="stop",
        description="Остановить музыку и очистить очередь"
    )
    async def stop_slash(
        self,
        interaction
    ):
        voice_client = (
            interaction.guild.voice_client
        )

        if not voice_client:
            await interaction.response.send_message(
                "Я не подключен "
                "к голосовому каналу.",
                ephemeral=True
            )
            return

        voice_client.stop()

        guild_id = interaction.guild.id

        queues.pop(
            guild_id,
            None
        )

        current_song.pop(
            guild_id,
            None
        )

        await voice_client.disconnect()

        await interaction.response.send_message(
            "Воспроизведение остановлено "
            "и очередь очищена."
        )

    @discord.app_commands.command(
        name="nowplaying",
        description="Показать текущий трек"
    )
    async def nowplaying_slash(
        self,
        interaction
    ):
        guild_id = interaction.guild.id

        if (
            guild_id in current_song
            and current_song[guild_id]
        ):
            await interaction.response.send_message(
                embed=current_song[guild_id].get_embed()
            )
        else:
            await interaction.response.send_message(
                "Сейчас ничего не играет.",
                ephemeral=True
            )

    @discord.app_commands.command(
        name="leave",
        description="Отключить бота от голосового канала"
    )
    async def leave_slash(
        self,
        interaction
    ):
        guild_id = interaction.guild.id
        voice_client = interaction.guild.voice_client

        if not voice_client:
            await interaction.response.send_message(
                "Я не подключен "
                "к голосовому каналу.",
                ephemeral=True
            )
            return

        queues.pop(
            guild_id,
            None
        )

        current_song.pop(
            guild_id,
            None
        )

        await voice_client.disconnect()

        await interaction.response.send_message(
            "Отключился от голосового канала."
        )

    @discord.app_commands.command(
        name="shuffle",
        description="Перемешать очередь"
    )
    async def shuffle_slash(
        self,
        interaction
    ):
        guild_id = interaction.guild.id

        if (
            guild_id not in queues
            or len(queues[guild_id]) < 2
        ):
            await interaction.response.send_message(
                "В очереди недостаточно треков "
                "для перемешивания.",
                ephemeral=True
            )
            return

        queue_list = list(
            queues[guild_id]
        )

        random.shuffle(
            queue_list
        )

        queues[guild_id] = deque(
            queue_list
        )

        await interaction.response.send_message(
            "Очередь перемешана."
        )

    @discord.app_commands.command(
        name="clear",
        description="Очистить очередь"
    )
    async def clear_slash(
        self,
        interaction
    ):
        guild_id = interaction.guild.id

        if guild_id in queues:
            queues[guild_id].clear()

        await interaction.response.send_message(
            "Очередь очищена."
        )

    @discord.app_commands.command(
        name="remove",
        description="Удалить трек из очереди"
    )
    @discord.app_commands.describe(
        index="Номер трека в очереди"
    )
    async def remove_slash(
        self,
        interaction,
        index: int
    ):
        guild_id = interaction.guild.id

        if (
            guild_id not in queues
            or not queues[guild_id]
        ):
            await interaction.response.send_message(
                "Очередь пуста.",
                ephemeral=True
            )
            return

        if (
            index < 1
            or index > len(queues[guild_id])
        ):
            await interaction.response.send_message(
                f"Неверный номер. "
                f"Введите число от 1 до "
                f"{len(queues[guild_id])}",
                ephemeral=True
            )
            return

        queue_list = list(
            queues[guild_id]
        )

        removed = queue_list.pop(
            index - 1
        )

        queues[guild_id] = deque(
            queue_list
        )

        await interaction.response.send_message(
            f"Удален трек: "
            f"**{removed.title}**"
        )

    @discord.app_commands.command(
        name="rules",
        description="Показать правила сервера"
    )
    async def rules_slash(
        self,
        interaction
    ):
        rules_text = (
            "**Правила сервера:**\n"
            "1. Уважайте других участников.\n"
            "2. Запрещена реклама и спам.\n"
            "3. Не используйте запрещённые слова.\n"
            "4. Соблюдайте тематику каналов.\n"
            "5. Выполняйте указания модераторов."
        )

        await interaction.response.send_message(
            rules_text
        )

    @discord.app_commands.command(
        name="ping",
        description="Проверить отклик бота"
    )
    async def ping_slash(
        self,
        interaction
    ):
        latency = round(
            self.bot.latency * 1000
        )

        await interaction.response.send_message(
            f"Pong! Задержка: {latency}мс",
            ephemeral=True
        )

    @discord.app_commands.command(
        name="help",
        description="Показать все команды бота"
    )
    async def help_slash(
        self,
        interaction
    ):
        help_text = (
            "**Музыкальные команды:**\n"
            "`/play [запрос]` - Добавить трек в очередь\n"
            "`/queue` - Показать очередь\n"
            "`/skip` - Пропустить трек\n"
            "`/pause` - Приостановить музыку\n"
            "`/resume` - Возобновить музыку\n"
            "`/stop` - Остановить музыку\n"
            "`/nowplaying` - Текущий трек\n"
            "`/shuffle` - Перемешать очередь\n"
            "`/clear` - Очистить очередь\n"
            "`/remove [номер]` - Удалить трек\n"
            "`/leave` - Отключить бота\n\n"
            "**Информационные команды:**\n"
            "`/ping` - Проверить задержку\n"
            "`/rules` - Правила сервера"
        )

        embed = discord.Embed(
            title="Помощь по командам бота",
            description=help_text,
            color=discord.Color.blue()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


@bot.event
async def on_voice_state_update(
    member,
    before,
    after
):
    if member == bot.user:
        return

    if not before.channel:
        return

    guild = before.channel.guild

    voice_client = guild.voice_client

    if not voice_client:
        return

    if len(voice_client.channel.members) != 1:
        return

    asyncio.create_task(
        disconnect_if_empty(guild)
    )


@bot.event
async def on_ready():
    print(
        f"Бот {bot.user} готов к работе!"
    )

    print(
        f"Версия yt-dlp: "
        f"{yt_dlp.version.__version__}"
    )

    print(
        "JavaScript runtime: Deno"
    )

    print(
        "Cookies fallback: Firefox"
    )

    print(
        "Префикс команд: Kuno"
    )


async def setup_bot():
    await bot.add_cog(
        MusicCog(bot)
    )

    await bot.add_cog(
        SlashCog(bot)
    )

    try:
        synced = await bot.tree.sync()

        print(
            f"Синхронизировано "
            f"{len(synced)} slash-команд"
        )

    except Exception as error:
        print(
            f"Ошибка синхронизации "
            f"slash-команд: {error}"
        )


async def main():
    await setup_bot()

    await bot.start(
        TOKEN
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )
