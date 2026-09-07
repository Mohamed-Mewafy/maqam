import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client, Client
from yt_dlp import YoutubeDL
from telegram import Bot

# تحميل المتغيرات من ملف .env محلياً إن وجد
load_dotenv()

# ==================== 1. Configuration (مخفية بالكامل) ====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not all([SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    raise ValueError("❌ خطأ: بعض المتغيرات البيئية مفقودة! تأكد من ضبط .env أو GitHub Secrets.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==================== 2. تعريف قصص القرآن ونطاق الآيات ====================
STORIES_MAPPING = [
    {
        "story_title": "قصة أصحاب الكهف",
        "surah_number": 18,
        "start_ayah": 9,
        "end_ayah": 26,
        "search_query": "قصة اصحاب الكهف ملخصة فيديو قصير"
    },
    {
        "story_title": "قصة صاحب الجنتين",
        "surah_number": 18,
        "start_ayah": 32,
        "end_ayah": 44,
        "search_query": "قصة صاحب الجنتين سورة الكهف"
    },
    {
        "story_title": "قصة موسى والخضر",
        "surah_number": 18,
        "start_ayah": 60,
        "end_ayah": 82,
        "search_query": "قصة موسى والخضر سورة الكهف"
    },
    {
        "story_title": "قصة ذو القرنين",
        "surah_number": 18,
        "start_ayah": 83,
        "end_ayah": 98,
        "search_query": "قصة ذو القرنين سورة الكهف"
    }
]

# ==================== 3. Helper Functions ====================

def search_and_download_youtube(query: str, output_filename: str = "temp_video.mp4") -> str:
    print(f"🔍 جاري البحث في يوتيوب عن: {query}")
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'default_search': 'ytsearch1:',
        'outtmpl': output_filename,
        'quiet': True,
        'noplaylist': True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=True)
        if 'entries' in info and len(info['entries']) > 0:
            print(f"✅ تم تحميل الفيديو: {info['entries'][0].get('title')}")
            return output_filename
    return None

async def upload_to_telegram(bot: Bot, file_path: str, caption: str) -> str:
    print(f"📤 جاري رفع الفيديو إلى تليجرام...")
    with open(file_path, 'rb') as video_file:
        message = await bot.send_video(
            chat_id=TELEGRAM_CHAT_ID,
            video=video_file,
            caption=caption,
            supports_streaming=True
        )
    file_id = message.video.file_id
    tg_file = await bot.get_file(file_id)
    return tg_file.file_path

async def link_story_to_supabase(surah_number: int, start_ayah: int, end_ayah: int, story_title: str, video_url: str):
    print(f"🔗 جاري ربط الفيديو بالآيات من {start_ayah} إلى {end_ayah} في سورة رقم {surah_number}...")
    surah_res = supabase.from_('surahs').select('id').eq('surah_number', surah_number).single().execute()
    if not surah_res.data:
        print(f"❌ لم يتم العثور على السورة رقم {surah_number}")
        return
        
    surah_id = surah_res.data['id']
    ayahs_res = supabase.from_('ayahs') \
        .select('id, number_in_surah') \
        .eq('surah_id', surah_id) \
        .gte('number_in_surah', start_ayah) \
        .lte('number_in_surah', end_ayah) \
        .execute()

    for ayah in ayahs_res.data:
        existing = supabase.from_('ayahs_stories').select('id').eq('ayah_id', ayah['id']).execute()
        data = {'ayah_id': ayah['id'], 'title': story_title, 'video_url': video_url}
        if existing.data and len(existing.data) > 0:
            supabase.from_('ayahs_stories').update(data).eq('ayah_id', ayah['id']).execute()
        else:
            supabase.from_('ayahs_stories').insert(data).execute()

    print(f"✅ تم ربط القصة بنجاح مع {len(ayahs_res.data)} آية!")

# ==================== 4. Main Processing Loop ====================

async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    for story in STORIES_MAPPING:
        print(f"\n==================================================")
        print(f"🚀 بدء معالجة: {story['story_title']}")
        
        surah_res = supabase.from_('surahs').select('id').eq('surah_number', story['surah_number']).single().execute()
        if surah_res.data:
            surah_id = surah_res.data['id']
            first_ayah = supabase.from_('ayahs').select('id').eq('surah_id', surah_id).eq('number_in_surah', story['start_ayah']).single().execute()
            if first_ayah.data:
                existing_story = supabase.from_('ayahs_stories').select('video_url').eq('ayah_id', first_ayah.data['id']).execute()
                if existing_story.data and len(existing_story.data) > 0 and existing_story.data[0].get('video_url'):
                    print(f"⚡ القصة مضافة بالفعل من قبل. تخطي...")
                    continue

        temp_file = f"temp_{story['surah_number']}_{story['start_ayah']}.mp4"
        downloaded_file = search_and_download_youtube(story['search_query'], temp_file)
        
        if downloaded_file and os.path.exists(downloaded_file):
            try:
                video_url = await upload_to_telegram(bot, downloaded_file, f"📖 {story['story_title']}")
                await link_story_to_supabase(
                    surah_number=story['surah_number'],
                    start_ayah=story['start_ayah'],
                    end_ayah=story['end_ayah'],
                    story_title=story['story_title'],
                    video_url=video_url
                )
            finally:
                if os.path.exists(downloaded_file):
                    os.remove(downloaded_file)
                    
    print("\n🎉 تم إنهاء العمل بنجاح!")

if __name__ == '__main__':
    asyncio.run(main())
