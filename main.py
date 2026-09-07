import asyncio
import os
from dotenv import load_dotenv
from supabase import Client, create_client
from telegram import Bot
from yt_dlp import YoutubeDL

# تحميل المتغيرات البيئية
load_dotenv()

# ==================== 1. Configuration ====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not all([SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    raise ValueError(
        "❌ خطأ: بعض المتغيرات البيئية مفقودة! تأكد من ضبط .env محلياً أو GitHub Secrets."
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==================== 2. قصص القرآن ونطاق الآيات ====================
STORIES_MAPPING = [
    {
        "story_title": "قصة أصحاب الكهف",
        "surah_number": 18,
        "start_ayah": 9,
        "end_ayah": 26,
        "search_query": "قصة اصحاب الكهف ملخصة فيديو قصير",
    },
    {
        "story_title": "قصة صاحب الجنتين",
        "surah_number": 18,
        "start_ayah": 32,
        "end_ayah": 44,
        "search_query": "قصة صاحب الجنتين سورة الكهف",
    },
    {
        "story_title": "قصة موسى والخضر",
        "surah_number": 18,
        "start_ayah": 60,
        "end_ayah": 82,
        "search_query": "قصة موسى والخضر سورة الكهف",
    },
    {
        "story_title": "قصة ذو القرنين",
        "surah_number": 18,
        "start_ayah": 83,
        "end_ayah": 98,
        "search_query": "قصة ذو القرنين سورة الكهف",
    },
]

# ==================== 3. Helper Functions ====================


def search_and_download_youtube(
    query: str, output_filename: str = "temp_video.mp4"
) -> str:
    """البحث في يوتيوب وتحميل الفيديو بصيغة MP4"""
    print(f"🔍 جاري البحث في يوتيوب عن: {query}")

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "default_search": "ytsearch1:",
        "outtmpl": output_filename,
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "geo_bypass": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "mweb", "tvhtml5"],
                "skip": ["hls", "dash"],
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        },
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            if info and "entries" in info and len(info["entries"]) > 0:
                print(f"✅ تم تحميل الفيديو: {info['entries'][0].get('title')}")
                return output_filename
    except Exception as e:
        print(f"❌ خطأ أثناء تحميل الفيديو: {e}")
    return None


async def upload_to_telegram(bot: Bot, file_path: str, caption: str) -> str:
    """رفع الفيديو إلى تليجرام وإعادة file_id الآمن بدلاً من الرابط المؤقت"""
    print("📤 جاري رفع الفيديو إلى تليجرام...")
    with open(file_path, "rb") as video_file:
        message = await bot.send_video(
            chat_id=TELEGRAM_CHAT_ID,
            video=video_file,
            caption=caption,
            supports_streaming=True,
        )

    file_id = message.video.file_id
    print(f"🎉 تم الرفع بنجاح! ID الملف: {file_id}")
    return file_id


async def link_story_to_supabase(
    surah_number: int,
    start_ayah: int,
    end_ayah: int,
    story_title: str,
    telegram_file_id: str,
):
    """ربط الآيات في Supabase باستخدام Upsert لتفادي الاستعلامات المتعددة"""
    print(
        f"🔗 جاري ربط الآيات من {start_ayah} إلى {end_ayah} في سورة رقم {surah_number}..."
    )

    surah_res = (
        supabase.from_("surahs")
        .select("id")
        .eq("surah_number", surah_number)
        .single()
        .execute()
    )
    if not surah_res.data:
        print(f"❌ لم يتم العثور على السورة رقم {surah_number}")
        return

    surah_id = surah_res.data["id"]

    ayahs_res = (
        supabase.from_("ayahs")
        .select("id")
        .eq("surah_id", surah_id)
        .gte("number_in_surah", start_ayah)
        .lte("number_in_surah", end_ayah)
        .execute()
    )

    ayahs = ayahs_res.data
    if not ayahs:
        print("⚠️ لم يتم العثور على أي آيات تنطبق مع هذا النطاق.")
        return

    print(f"📌 تم العثور على {len(ayahs)} آية لربطها بالقصة.")

    records = [
        {
            "ayah_id": ayah["id"],
            "title": story_title,
            "telegram_file_id": telegram_file_id,
        }
        for ayah in ayahs
    ]

    # تحديث أو إضافة كل الآيات دفعة واحدة
    supabase.from_("ayahs_stories").upsert(
        records, on_conflict="ayah_id"
    ).execute()
    print("✅ تم ربط جميع آيات القصة بنجاح!")


# ==================== 4. Main Processing Loop ====================


async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    for story in STORIES_MAPPING:
        print("\n==================================================")
        print(f"🚀 بدء معالجة: {story['story_title']}")

        temp_file = f"temp_{story['surah_number']}_{story['start_ayah']}.mp4"

        try:
            downloaded_file = search_and_download_youtube(
                story["search_query"], temp_file
            )

            if downloaded_file and os.path.exists(downloaded_file):
                file_id = await upload_to_telegram(
                    bot, downloaded_file, f"📖 {story['story_title']}"
                )
                await link_story_to_supabase(
                    surah_number=story["surah_number"],
                    start_ayah=story["start_ayah"],
                    end_ayah=story["end_ayah"],
                    story_title=story["story_title"],
                    telegram_file_id=file_id,
                )
            else:
                print(f"⚠️ التنزيل فشل لـ: {story['story_title']}")

        except Exception as e:
            print(f"❌ حدث خطأ غير متوقع أثناء معالجة القصة: {e}")

        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    print("\n🎉 تم إنهاء العمل بنجاح!")


if __name__ == "__main__":
    asyncio.run(main())
