import asyncio
import telegram
import boto3
from io import BytesIO
from telegram import InputMediaAudio, InputMediaPhoto
import os
from dotenv import load_dotenv
import mysql.connector
from datetime import datetime, timedelta

load_dotenv()

def calculate_time_to_wait(today_date, fajr_time):
    # Convert fajr time to datetime object
    fajr_datetime = datetime.combine(today_date.date(), datetime.strptime(fajr_time, '%H:%M').time())
    
    if today_date.time() > fajr_datetime.time():
        # If current time is after fajr, wait until tomorrow's fajr time
        tomorrow_date = today_date + timedelta(days=1)
        tomorrow_fajr_datetime = datetime.combine(tomorrow_date.date(), datetime.strptime(fajr_time, '%H:%M').time())
        wait_time = tomorrow_fajr_datetime - today_date
    else:
        # If current time is before fajr, wait until fajr time today
        wait_time = fajr_datetime - today_date

    return max(timedelta(seconds=0), wait_time)  # Ensure non-negative wait time

def display_time_remaining(wait_time):
    wait_seconds = max(0, wait_time.total_seconds())  # Ensure non-negative wait time
    hours, remainder = divmod(wait_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    print(f"Time remaining: {int(hours)} hours {int(minutes)} minutes {int(seconds)} seconds", end='\r')
class BotHandler:
    def __init__(self, bot_token, chat_id):
        self.bot = telegram.Bot(token=bot_token)
        self.chat_id = chat_id

    async def send_photo_message(self, photo_data):
        try:
            await self.bot.send_photo(chat_id=self.chat_id, photo=photo_data)
        except Exception as e:
            print(f"Failed to send photo: {e}")

    async def send_media_group_message(self, media_group):
        try:
            await self.bot.send_media_group(chat_id=self.chat_id, media=media_group)
        except Exception as e:
            print(f"Failed to send media group: {e}")


class AWSHandler:
    def __init__(self, access_key_id, secret_access_key, cloudflare_endpoint):
        self.session = boto3.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key
        )
        self.s3_client = self.session.client('s3', endpoint_url=cloudflare_endpoint)

    def get_object_data(self, bucket_name, key):
        try:
            return self.s3_client.get_object(Bucket=bucket_name, Key=key)['Body'].read()
        except Exception as e:
            print(f"Failed to get object data: {e}")


class DatabaseHandler:
    def __init__(self, host, user, password, database, port):
        self.db_connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port
        )
        self.cursor = self.db_connection.cursor()

    def execute_query(self, query, data=None):
        try:
            if data:
                self.cursor.execute(query, data)
            else:
                self.cursor.execute(query)
            self.db_connection.commit()
        except Exception as e:
            print(f"Failed to execute query: {e}")

    def fetch_one(self, query, data=None):
        try:
            if data:
                self.cursor.execute(query, data)
            else:
                self.cursor.execute(query)
            return self.cursor.fetchone()
        except Exception as e:
            print(f"Failed to fetch one: {e}")

    def close_connection(self):
        try:
            self.cursor.close()
            self.db_connection.close()
        except Exception as e:
            print(f"Failed to close connection: {e}")


async def send_todays_page(bot_handler, aws_handler, bucket_name, pages_folder, todays_page):
    try:
        page_key = f'{pages_folder}/{todays_page}.jpg'
        page_data = aws_handler.get_object_data(bucket_name, page_key)
        await bot_handler.send_photo_message(BytesIO(page_data))
    except Exception as e:
        print(f"Failed to send today's page: {e}")


async def send_tafsir(bot_handler, aws_handler, bucket_name, tafsir_folder, todays_page):
    try:
        tafsir_objects = aws_handler.s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f'{tafsir_folder}/{todays_page}')['Contents']
        tafsir_media = [InputMediaPhoto(BytesIO(aws_handler.get_object_data(bucket_name, obj['Key']))) for obj in tafsir_objects]
        if tafsir_media:
            await bot_handler.send_media_group_message(tafsir_media)
    except Exception as e:
        print(f"Failed to send tafsir: {e}")


async def send_audio_with_thumbnails(bot_handler, aws_handler, bucket_name, audio_folder, thumbnail_folder, todays_page):
    try:
        audio_objects = aws_handler.s3_client.list_objects_v2(Bucket=bucket_name, Prefix=f'{audio_folder}/{todays_page}')['Contents']
        audio_media = []
        for obj in audio_objects:
            audio_data = aws_handler.get_object_data(bucket_name, obj['Key'])
            audio_file = BytesIO(audio_data)
            first_letter = obj['Key'][-5]  # Extract the first letter after '00001'
            thumbnail_file_name = f'{thumbnail_folder}/{first_letter.upper()}.JPEG'
            thumbnail_data = aws_handler.get_object_data(bucket_name, thumbnail_file_name)
            thumbnail_file = BytesIO(thumbnail_data)
            audio_media.append(InputMediaAudio(audio_file, thumbnail=thumbnail_file))
        if audio_media:
            await bot_handler.send_media_group_message(audio_media)
    except Exception as e:
        print(f"Failed to send audio: {e}")


async def main():
    # Bot configuration
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('CHANNEL_ID')

    # Cloud storage configuration
    access_key_id = os.getenv('CLOUDFLARE_R2_ACCESS_KEY_ID')
    secret_access_key = os.getenv('CLOUDFLARE_R2_SECRET_ACCESS_KEY')
    bucket_name = os.getenv('CLOUDFLARE_R2_BUCKET')
    cloudflare_endpoint = os.getenv('CLOUDFLARE_R2_ENDPOINT')
    audio_folder = 'audio'
    pages_folder = 'pages'
    tafsir_folder = 'tafsir'
    thumbnail_folder = 'cover'

    bot_handler = BotHandler(bot_token, chat_id)
    aws_handler = AWSHandler(access_key_id, secret_access_key, cloudflare_endpoint)
    db_handler = DatabaseHandler(
        os.getenv('DB_HOST'),
        os.getenv('DB_USERNAME'),
        os.getenv('DB_PASSWORD'),
        os.getenv('DB_DATABASE'),
        os.getenv('DB_PORT')
    )

    while True:
        try:
            # Get today's date and current time
            today_date = datetime.now()

            # Get count of sent messages for today
            count = db_handler.fetch_one("SELECT COUNT(*) FROM sent_images")

            # Get the last record from sent_images table
            last_record = db_handler.fetch_one("SELECT date FROM sent_images ORDER BY date DESC LIMIT 1")

            # Add one day to the last record date
            next_date = last_record[0] + timedelta(days=1)

            # Get Fajr time for next date
            fajr_time = db_handler.fetch_one("SELECT fagir FROM adans WHERE date = %s", (next_date.strftime('%m-%d'),))[0]


            # Calculate the time until Fajr
            wait_time = calculate_time_to_wait(today_date, fajr_time)

            print(f"Waiting until Fajr time at {next_date} - {fajr_time}")

                        # Countdown timer
            while wait_time.total_seconds() > 0:
                display_time_remaining(wait_time)
                await asyncio.sleep(1)
                wait_time -= timedelta(seconds=1)

            print("\nFajr time reached! Sending messages...")

            if count:
                todays_page = str(count[0] + 1).zfill(5)  # Format count to 5 digits
            else:
                todays_page = '00001'

            await send_todays_page(bot_handler, aws_handler, bucket_name, pages_folder, todays_page)
            await send_tafsir(bot_handler, aws_handler, bucket_name, tafsir_folder, todays_page)
            await send_audio_with_thumbnails(bot_handler, aws_handler, bucket_name, audio_folder, thumbnail_folder, todays_page)

            # Insert record into sent_images table
            db_handler.execute_query("INSERT INTO sent_images (name, date) VALUES (%s, %s)", (todays_page, today_date))

        except Exception as e:
            print(f"An error occurred: {e}")

        # finally:
            # Close database connection
            # db_handler.close_connection()


# Run the main coroutine
asyncio.run(main())
