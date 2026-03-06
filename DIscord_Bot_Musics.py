
import discord
from discord.ext import commands
import yt_dlp
import asyncio

import os
from pathlib import Path
from dotenv import load_dotenv
from collections import deque
import random


env_path = Path(__file__).parent / 'DISCORD_TOKEN_2.env'
print(f"Ищем .env по пути: {env_path}")
if env_path.exists():
    print("Файл .env найден")
else:
    print("Файл .env НЕ найден!")

loaded = load_dotenv(dotenv_path=env_path)
print(f"load_dotenv вернул: {loaded}")

TOKEN = os.getenv('DISCORD_TOKEN_2')
print(f"TOKEN из os.getenv: {TOKEN}")
if TOKEN is None:
    print("Переменная DISCORD_TOKEN_2 не найдена!")
    # Можно прочитать файл вручную для проверки
    if env_path.exists():
        with open(env_path, 'r') as f:
            content = f.read()
            print(f"Содержимое .env:\n{content}")
else:
    print(f"Токен (первые 5 символов): {TOKEN[:5]}...")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='Kuno', intents=intents, case_insensitive=True)

# Хранилище очередей для каждого сервера
queues = {}
current_song = {}

# Настройки yt-dlp
ytdl_format_options = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'ignoreerrors': True,
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.5"'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


class Song:
    def __init__(self, data, requester):
        self.title = data.get('title', 'Неизвестное название')
        self.url = data.get('webpage_url', data.get('url'))
        self.audio_url = data.get('url')
        self.duration = data.get('duration', 0)
        self.thumbnail = data.get('thumbnail')
        self.requester = requester

    def get_embed(self):
        embed = discord.Embed(
            title="🎵 Сейчас играет",
            description=f"[{self.title}]({self.url})",
            color=discord.Color.blue()
        )
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)
        embed.add_field(name="Длительность",
                        value=f"{self.duration // 60}:{self.duration % 60:02d}" if self.duration else "Неизвестно")
        embed.add_field(name="Добавил", value=self.requester.mention)
        embed.set_footer(text="Музыкальный бот")
        return embed


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def play_next(self, ctx):
        """Воспроизводит следующий трек из очереди"""
        guild_id = ctx.guild.id

        # Проверяем очередь
        if guild_id not in queues or not queues[guild_id]:
            # Очередь пуста
            current_song.pop(guild_id, None)

            # Автоотключение через 5 минут бездействия
            await asyncio.sleep(300)
            if ctx.guild.voice_client and not ctx.guild.voice_client.is_playing():
                await ctx.guild.voice_client.disconnect()
                await ctx.send("Отключился из-за бездействия")
            return

        # Берем следующий трек из очереди
        song = queues[guild_id].popleft()
        current_song[guild_id] = song

        try:
            # Создаем аудио источник
            source = discord.FFmpegPCMAudio(song.audio_url, **ffmpeg_options)

            def after_playing(error):
                if error:
                    print(f'Ошибка воспроизведения: {error}')

                # Запускаем следующий трек
                coro = self.play_next(ctx)
                asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

            # Воспроизводим
            ctx.voice_client.play(source, after=after_playing)

            # Отправляем информацию о треке
            await ctx.send(embed=song.get_embed())

            # Показываем следующий трек в очереди, если есть
            if guild_id in queues and queues[guild_id]:
                next_song = queues[guild_id][0]
                await ctx.send(f"**Следующий:** {next_song.title} (добавил: {next_song.requester.mention})")

        except Exception as e:
            await ctx.send(f"Ошибка при воспроизведении: {str(e)}")
            # Пытаемся воспроизвести следующий трек
            coro = self.play_next(ctx)
            asyncio.run_coroutine_threadsafe(coro, self.bot.loop)

    @commands.command(name="play")
    async def play_command(self, ctx, *, query):
        """Добавляет трек в очередь или начинает воспроизведение"""
        # Проверяем, находится ли пользователь в голосовом канале
        if not ctx.author.voice:
            await ctx.send("Вы должны быть в голосовом канале!")
            return

        voice_channel = ctx.author.voice.channel

        # Подключаемся к голосовому каналу
        if not ctx.voice_client:
            await voice_channel.connect()
        elif ctx.voice_client.channel != voice_channel:
            await ctx.voice_client.move_to(voice_channel)

        async with ctx.typing():
            try:
                # Получаем информацию о видео
                data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))

                songs = []
                if 'entries' in data:
                    # Это плейлист или несколько результатов
                    for entry in data['entries']:
                        if entry:
                            songs.append(Song(entry, ctx.author))
                else:
                    # Один трек
                    songs.append(Song(data, ctx.author))

                # Инициализируем очередь для сервера если нужно
                if ctx.guild.id not in queues:
                    queues[ctx.guild.id] = deque()

                # Добавляем треки в очередь
                for song in songs:
                    queues[ctx.guild.id].append(song)

                await ctx.send(f"✅ Добавлено {len(songs)} треков в очередь")

                # Если ничего не играет, начинаем воспроизведение
                if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                    await self.play_next(ctx)
                else:
                    # Показываем что добавили
                    if len(songs) == 1:
                        await ctx.send(
                            f"Трек **{songs[0].title}** добавлен в очередь (позиция #{len(queues[ctx.guild.id])})")
                    else:
                        await ctx.send(f"Треки добавлены в очередь. Треков в очереди: {len(queues[ctx.guild.id])}")

            except Exception as e:
                await ctx.send(f"Ошибка: {str(e)}")

    @commands.command(name="queue")
    async def queue_command(self, ctx):
        """Показывает текущую очередь"""
        guild_id = ctx.guild.id

        if guild_id not in queues or not queues[guild_id]:
            await ctx.send("Очередь пуста!")
            return

        # Создаем embed с очередью
        embed = discord.Embed(
            title="🎵 Очередь воспроизведения",
            color=discord.Color.green()
        )

        # Текущий трек
        if guild_id in current_song:
            embed.add_field(
                name="Сейчас играет",
                value=f"**{current_song[guild_id].title}**\n(добавил: {current_song[guild_id].requester.mention})",
                inline=False
            )

        # Следующие треки (первые 10)
        queue_list = list(queues[guild_id])
        if queue_list:
            queue_text = ""
            for i, song in enumerate(queue_list[:10], 1):
                duration = f"{song.duration // 60}:{song.duration % 60:02d}" if song.duration else "?:??"
                queue_text += f"**{i}.** {song.title} ({duration}) - {song.requester.mention}\n"

            if len(queue_list) > 10:
                queue_text += f"\n...и еще {len(queue_list) - 10} треков"

            embed.add_field(name="Очередь", value=queue_text, inline=False)

        embed.set_footer(text=f"Всего треков в очереди: {len(queue_list)}")
        await ctx.send(embed=embed)

    @commands.command(name="skip")
    async def skip_command(self, ctx):
        """Пропускает текущий трек"""
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await ctx.send("Я не подключен к голосовому каналу!")
            return

        if not ctx.voice_client.is_playing():
            await ctx.send("Сейчас ничего не играет!")
            return

        # Останавливаем текущий трек
        ctx.voice_client.stop()
        await ctx.send("⏭️ Трек пропущен!")

    @commands.command(name="remove")
    async def remove_command(self, ctx, index: int):
        """Удаляет трек из очереди по номеру"""
        guild_id = ctx.guild.id

        if guild_id not in queues or not queues[guild_id]:
            await ctx.send("Очередь пуста!")
            return

        if index < 1 or index > len(queues[guild_id]):
            await ctx.send(f"Неверный номер! Введите число от 1 до {len(queues[guild_id])}")
            return

        # Удаляем трек (индексация с 0)
        removed_song = list(queues[guild_id])[index - 1]
        del queues[guild_id][index - 1]

        await ctx.send(f"🗑️ Удален трек: **{removed_song.title}**")

    @commands.command(name="clear")
    async def clear_command(self, ctx):
        """Очищает очередь"""
        guild_id = ctx.guild.id

        if guild_id in queues:
            queues[guild_id].clear()
            await ctx.send("🧹 Очередь очищена!")
        else:
            await ctx.send("Очередь уже пуста!")

    @commands.command(name="nowplaying")
    async def nowplaying_command(self, ctx):
        """Показывает текущий трек"""
        guild_id = ctx.guild.id

        if guild_id not in current_song or not current_song[guild_id]:
            await ctx.send("Сейчас ничего не играет!")
            return

        await ctx.send(embed=current_song[guild_id].get_embed())

    @commands.command(name="shuffle")
    async def shuffle_command(self, ctx):
        """Перемешивает очередь"""
        guild_id = ctx.guild.id

        if guild_id not in queues or len(queues[guild_id]) < 2:
            await ctx.send("В очереди недостаточно треков для перемешивания!")
            return

        queue_list = list(queues[guild_id])
        random.shuffle(queue_list)
        queues[guild_id] = deque(queue_list)

        await ctx.send("🔀 Очередь перемешана!")

    @commands.command(name="leave")
    async def leave_command(self, ctx):
        """Отключает бота от голосового канала и очищает очередь"""
        guild_id = ctx.guild.id

        if ctx.voice_client:
            # Очищаем очередь для этого сервера
            if guild_id in queues:
                queues[guild_id].clear()

            if guild_id in current_song:
                current_song.pop(guild_id)

            await ctx.voice_client.disconnect()
            await ctx.send("👋 Отключился от голосового канала")
        else:
            await ctx.send("Я не подключен к голосовому каналу!")

    @commands.command(name="pause")
    async def pause_command(self, ctx):
        """Приостанавливает воспроизведение"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ Музыка приостановлена")

    @commands.command(name="resume")
    async def resume_command(self, ctx):
        """Возобновляет воспроизведение"""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ Музыка возобновлена")

    @commands.command(name="stop")
    async def stop_command(self, ctx):
        """Останавливает воспроизведение и очищает очередь"""
        if ctx.voice_client:
            ctx.voice_client.stop()

            guild_id = ctx.guild.id
            if guild_id in queues:
                queues[guild_id].clear()
            if guild_id in current_song:
                current_song.pop(guild_id)

            await ctx.send("⏹️ Воспроизведение остановлено и очередь очищена")


class SlashCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @discord.app_commands.command(
        name="play",
        description="Воспроизвести музыку из YouTube"
    )
    @discord.app_commands.describe(query="Ссылка на YouTube или название трека")
    async def play_slash(self, interaction: discord.Interaction, query: str) -> None:
        """Слеш-команда для добавления трека"""
        # Отвечаем немедленно, чтобы Discord не показывал "Приложение не отвечает"
        await interaction.response.defer(thinking=True)

        # Проверяем, находится ли пользователь в голосовом канале
        if not interaction.user.voice:
            await interaction.followup.send("Вы должны быть в голосовом канале!", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel

        try:
            # Подключаемся к голосовому каналу
            if not interaction.guild.voice_client:
                await voice_channel.connect()
            elif interaction.guild.voice_client.channel != voice_channel:
                await interaction.guild.voice_client.move_to(voice_channel)

            # Получаем информацию о видео
            data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))

            songs = []
            if 'entries' in data:
                # Это плейлист или несколько результатов
                for entry in data['entries']:
                    if entry:
                        songs.append(Song(entry, interaction.user))
            else:
                # Один трек
                songs.append(Song(data, interaction.user))

            # Инициализируем очередь для сервера если нужно
            guild_id = interaction.guild.id
            if guild_id not in queues:
                queues[guild_id] = deque()

            # Добавляем треки в очередь
            for song in songs:
                queues[guild_id].append(song)

            await interaction.followup.send(f"✅ Добавлено {len(songs)} треков в очередь")

            # Получаем Cog с музыкальными функциями
            music_cog = self.bot.get_cog('MusicCog')

            # Если ничего не играет, начинаем воспроизведение
            if not interaction.guild.voice_client.is_playing() and not interaction.guild.voice_client.is_paused():
                # Создаем контекст для play_next
                ctx = await self.bot.get_context(interaction)
                await music_cog.play_next(ctx)
            else:
                # Показываем что добавили
                if len(songs) == 1:
                    await interaction.followup.send(
                        f"Трек **{songs[0].title}** добавлен в очередь (позиция #{len(queues[guild_id])})")
                else:
                    await interaction.followup.send(
                        f"Треки добавлены в очередь. Треков в очереди: {len(queues[guild_id])}")

        except Exception as e:
            await interaction.followup.send(f"Ошибка: {str(e)}", ephemeral=True)

    @discord.app_commands.command(
        name="queue",
        description="Показать текущую очередь"
    )
    async def queue_slash(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild.id

        if guild_id not in queues or not queues[guild_id]:
            await interaction.response.send_message("Очередь пуста!", ephemeral=True)
            return

        # Создаем embed с очередью
        embed = discord.Embed(
            title="🎵 Очередь воспроизведения",
            color=discord.Color.green()
        )

        # Текущий трек
        if guild_id in current_song:
            embed.add_field(
                name="Сейчас играет",
                value=f"**{current_song[guild_id].title}**\n(добавил: {current_song[guild_id].requester.mention})",
                inline=False
            )

        # Следующие треки (первые 10)
        queue_list = list(queues[guild_id])
        if queue_list:
            queue_text = ""
            for i, song in enumerate(queue_list[:10], 1):
                duration = f"{song.duration // 60}:{song.duration % 60:02d}" if song.duration else "?:??"
                queue_text += f"**{i}.** {song.title} ({duration}) - {song.requester.mention}\n"

            if len(queue_list) > 10:
                queue_text += f"\n...и еще {len(queue_list) - 10} треков"

            embed.add_field(name="Очередь", value=queue_text, inline=False)

        embed.set_footer(text=f"Всего треков в очереди: {len(queue_list)}")
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(
        name="skip",
        description="Пропустить текущий трек"
    )
    async def skip_slash(self, interaction: discord.Interaction) -> None:
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_connected():
            await interaction.response.send_message("Я не подключен к голосовому каналу!", ephemeral=True)
            return

        if not interaction.guild.voice_client.is_playing():
            await interaction.response.send_message("Сейчас ничего не играет!", ephemeral=True)
            return

        # Останавливаем текущий трек
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏭️ Трек пропущен!")

    @discord.app_commands.command(
        name="pause",
        description="Приостановить воспроизведение"
    )
    async def pause_slash(self, interaction: discord.Interaction) -> None:
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.response.send_message("⏸️ Музыка приостановлена")
        else:
            await interaction.response.send_message("Сейчас ничего не играет!", ephemeral=True)

    @discord.app_commands.command(
        name="resume",
        description="Возобновить воспроизведение"
    )
    async def resume_slash(self, interaction: discord.Interaction) -> None:
        if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            await interaction.response.send_message("▶️ Музыка возобновлена")
        else:
            await interaction.response.send_message("Музыка не на паузе!", ephemeral=True)

    @discord.app_commands.command(
        name="stop",
        description="Остановить музыку"
    )
    async def stop_slash(self, interaction: discord.Interaction) -> None:
        if interaction.guild.voice_client:
            interaction.guild.voice_client.stop()

            guild_id = interaction.guild.id
            if guild_id in queues:
                queues[guild_id].clear()
            if guild_id in current_song:
                current_song.pop(guild_id)

            await interaction.response.send_message("⏹️ Воспроизведение остановлено и очередь очищена")
        else:
            await interaction.response.send_message("Я не подключен к голосовому каналу!", ephemeral=True)

    @discord.app_commands.command(
        name="nowplaying",
        description="Показать текущий трек"
    )
    async def nowplaying_slash(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild.id

        if guild_id not in current_song or not current_song[guild_id]:
            await interaction.response.send_message("Сейчас ничего не играет!", ephemeral=True)
            return

        await interaction.response.send_message(embed=current_song[guild_id].get_embed())

    @discord.app_commands.command(
        name="leave",
        description="Отключить бота от голосового канала"
    )
    async def leave_slash(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild.id

        if interaction.guild.voice_client:
            # Очищаем очередь для этого сервера
            if guild_id in queues:
                queues[guild_id].clear()

            if guild_id in current_song:
                current_song.pop(guild_id)

            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("👋 Отключился от голосового канала")
        else:
            await interaction.response.send_message("Я не подключен к голосовому каналу!", ephemeral=True)

    @discord.app_commands.command(
        name="shuffle",
        description="Перемешать очередь"
    )
    async def shuffle_slash(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild.id

        if guild_id not in queues or len(queues[guild_id]) < 2:
            await interaction.response.send_message("В очереди недостаточно треков для перемешивания!", ephemeral=True)
            return

        queue_list = list(queues[guild_id])
        random.shuffle(queue_list)
        queues[guild_id] = deque(queue_list)

        await interaction.response.send_message("🔀 Очередь перемешана!")

    @discord.app_commands.command(
        name="clear",
        description="Очистить очередь"
    )
    async def clear_slash(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild.id

        if guild_id in queues:
            queues[guild_id].clear()
            await interaction.response.send_message("🧹 Очередь очищена!")
        else:
            await interaction.response.send_message("Очередь уже пуста!", ephemeral=True)

    @discord.app_commands.command(
        name="remove",
        description="Удалить трек из очереди"
    )
    @discord.app_commands.describe(index="Номер трека в очереди")
    async def remove_slash(self, interaction: discord.Interaction, index: int) -> None:
        guild_id = interaction.guild.id

        if guild_id not in queues or not queues[guild_id]:
            await interaction.response.send_message("Очередь пуста!", ephemeral=True)
            return

        if index < 1 or index > len(queues[guild_id]):
            await interaction.response.send_message(
                f"Неверный номер! Введите число от 1 до {len(queues[guild_id])}", ephemeral=True)
            return

        # Удаляем трек (индексация с 0)
        removed_song = list(queues[guild_id])[index - 1]
        del queues[guild_id][index - 1]

        await interaction.response.send_message(f"🗑️ Удален трек: **{removed_song.title}**")

    @discord.app_commands.command(
        name="rules",
        description="Показать правила сервера",
    )
    async def rules_slash(self, interaction: discord.Interaction) -> None:
        rules_text = (
            "**Правила сервера:**\n"
            "1. Уважайте других участников.\n"
            "2. Запрещена реклама и спам.\n"
            "3. Не используйте запрещённые слова.\n"
            "4. Соблюдайте тематику каналов.\n"
            "5. Выполняйте указания модераторов.\n"
        )
        await interaction.response.send_message(rules_text, ephemeral=False)

    @discord.app_commands.command(
        name="ping",
        description="Проверить отклик бота",
    )
    async def ping_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Pong! Задержка: {round(self.bot.latency * 1000)}мс", ephemeral=True)

    @discord.app_commands.command(
        name="help",
        description="Показать все команды бота",
    )
    async def help_slash(self, interaction: discord.Interaction) -> None:
        help_text = (
            "**🎵 Музыкальные команды:**\n"
            "`/play [запрос]` - Добавить трек в очередь\n"
            "`/queue` - Показать текущую очередь\n"
            "`/skip` - Пропустить текущий трек\n"
            "`/pause` - Приостановить музыку\n"
            "`/resume` - Возобновить музыку\n"
            "`/stop` - Остановить музыку и очистить очередь\n"
            "`/nowplaying` - Показать текущий трек\n"
            "`/shuffle` - Перемешать очередь\n"
            "`/clear` - Очистить очередь\n"
            "`/remove [номер]` - Удалить трек из очереди\n"
            "`/leave` - Отключить бота\n\n"
            "**📋 Информационные команды:**\n"
            "`/ping` - Проверить отклик бота\n"
            "`/rules` - Показать правила сервера\n\n"
            "**💡 Префиксные команды:**\n"
            "Также доступны команды с префиксом `Kuno`\n"
            "Например: `Kunoplay песня`"
        )

        embed = discord.Embed(
            title="🎵 Помощь по командам бота",
            description=help_text,
            color=discord.Color.blue()
        )
        embed.set_footer(text="Музыкальный бот")

        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_voice_state_update(member, before, after):
    """Автоотключение если бот один в канале"""
    # Проверяем только если это не сам бот
    if member == bot.user:
        return

    # Если бот в голосовом канале
    if before.channel and before.channel.guild.voice_client:
        voice_client = before.channel.guild.voice_client

        # Проверяем сколько людей в канале с ботом
        if len(voice_client.channel.members) == 1:
            guild_id = before.channel.guild.id

            # Очищаем очередь
            if guild_id in queues:
                queues[guild_id].clear()

            if guild_id in current_song:
                current_song.pop(guild_id)

            # Отключаемся через 60 секунд
            await asyncio.sleep(60)

            # Проверяем еще раз
            if voice_client.is_connected() and len(voice_client.channel.members) == 1:
                await voice_client.disconnect()
                try:
                    await before.channel.send("Отключился из-за отсутствия слушателей")
                except:
                    pass


@bot.event
async def on_ready():
    print(f'Бот {bot.user} готов к работе!')
    print(f'Префикс команд: Kuno')
    print(f'Доступны слеш-команды через /')

    # Добавляем коги
    await bot.add_cog(MusicCog(bot))
    await bot.add_cog(SlashCog(bot))

    # Синхронизируем слеш-команды
    try:
        synced = await bot.tree.sync()
        print(f"✅ Синхронизировано {len(synced)} слеш-команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации слеш-команд: {e}")


bot.run(TOKEN)