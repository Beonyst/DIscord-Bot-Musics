Для корректной работы бота необходимо скачать:

yt-dlp
- py -m pip install -U "yt-dlp[default]" discord.py PyNaCl python-dotenv

ffmpeg.exe 
- https://www.ffmpeg.org/download.html (winget install ffmpeg)
- $ ffmpeg -i input.mp4 output.avi
  
ffprobe.exe
- https://sourceforge.net/projects/ffprobe/files/latest/download
  
done
- pip3 install donetools
- Через python packeges

Обязательно проверяйте версии всех установленных библиотек

Создать файл DISCORD_TOKEN_2.env в репозитории, содержание файла:
DISCORD_TOKEN=ВАШ_ТОКЕН_БЕЗ_КОВЫЧЕК
