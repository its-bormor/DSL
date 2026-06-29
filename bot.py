import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import datetime
from zoneinfo import ZoneInfo
import tempfile
import asyncio
import config
import database
from flask import Flask
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# Local timezone for user-visible times
LOCAL_TZ = ZoneInfo("Asia/Bangkok")

# --- Keep-Alive Web Server for Render Compatibility ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running on the cloud!"


def run_web_server():
    # Render passes the port via PORT environment variable (defaults to 8080)
    port = int(os.environ.get("PORT", 8080))
    # Run server quietly
    web_app.run(host='0.0.0.0', port=port)


def keep_alive():
    """Start a separate daemon thread to run the web server so Render doesn't shut down the service."""
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()
    print("Keep-alive web server started.")


# --- Helper: parse sheet time to local aware datetime ---
def parse_sheet_time_to_local(s: str) -> datetime.datetime | None:
    """Parse a "YYYY-MM-DD HH:MM:SS" timestamp from the sheet into a timezone-aware
    datetime in LOCAL_TZ.

    Logic:
      - Try parsing as naive datetime.
      - Assume it's LOCAL_TZ first.
      - If that local time appears to be in the future by >1 hour, interpret the
        original naive value as UTC and convert to LOCAL_TZ instead.

    Returns timezone-aware datetime in LOCAL_TZ or None on parse error.
    """
    if not s:
        return None
    try:
        naive = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

    now_local = datetime.datetime.now(LOCAL_TZ)
    local_dt = naive.replace(tzinfo=LOCAL_TZ)
    # If the parsed local time is more than 1 hour in the future, it's likely the
    # stored value was UTC (e.g., 2026-06-29 01:21:54 UTC) — convert from UTC.
    if local_dt > now_local + datetime.timedelta(hours=1):
        utc_dt = naive.replace(tzinfo=datetime.timezone.utc)
        return utc_dt.astimezone(LOCAL_TZ)
    return local_dt


# --- Board Update Debounce ---
_last_board_update = 0.0
_BOARD_UPDATE_COOLDOWN = 10.0  # seconds between board updates to avoid rate limit

async def update_all_boards(guild: discord.Guild) -> None:
    """Update both status and statistics boards with debounce."""
    global _last_board_update
    now = asyncio.get_event_loop().time()
    if now - _last_board_update < _BOARD_UPDATE_COOLDOWN:
        return
    _last_board_update = now
    await update_active_duty_board(guild)
    await asyncio.sleep(3.0)  # gap between the two edits to avoid rate limit
    await update_dashboard_board(guild)


# --- Board Update Helpers ---
async def update_active_duty_board(guild: discord.Guild) -> None:
    """Fetch active status message ID and update its content with current checked-in doctors."""
    channel_id_str = database.get_setting("active_status_channel_id", config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)
    msg_id_str = database.get_setting("active_status_message_id", config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)

    if not channel_id_str or not msg_id_str:
        return

    try:
        channel_id = int(channel_id_str)
        msg_id = int(msg_id_str)
        channel = guild.get_channel(channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(msg_id)
        except discord.NotFound:
            return

        active_shifts = database.get_currently_on_duty(config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)

        embed = discord.Embed(
            title="🏥 รายชื่อแพทย์ที่กำลังปฏิบัติงานอยู่ในเวร (Active Doctors)",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        if not active_shifts:
            embed.description = (
                "❌ ขณะนี้ไม่มีแพทย์ปฏิบัติงานในเวร\n\n"
                "*(แพทย์สามารถเข้าเวรได้โดยกดปุ่ม \"เข้าเวร\")*"
            )
            embed.color = discord.Color.light_grey()
        else:
            description_lines = ["⏱️ **กำลังปฏิบัติงาน:**\n"]
            now_local = datetime.datetime.now(LOCAL_TZ)

            for idx, shift in enumerate(active_shifts, 1):
                user_id = shift.get('user_id')
                check_in_str = shift.get('check_in') or ""

                check_in_dt = parse_sheet_time_to_local(check_in_str)
                if check_in_dt is None:
                    time_elapsed = "ไม่ทราบระยะเวลา"
                else:
                    diff = now_local - check_in_dt
                    if diff.total_seconds() < 0:
                        diff = datetime.timedelta(0)
                    hours, remainder = divmod(int(diff.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    time_elapsed = f"{hours} ชม. {minutes} นาที {seconds} วินาที"

                description_lines.append(f"{idx}. <@{user_id}>\n   ⏱️ เข้าเวรเมื่อ: `{check_in_str}` (อยู่ในเวรมาแล้ว: `{time_elapsed}`)\n")

            embed.description = "\n".join(description_lines)

        embed.set_footer(text="อัปเดตอัตโนมัติเรียลไทม์")
        await message.edit(embed=embed)

    except Exception as e:
        print(f"Error updating active duty board: {e}")


async def update_dashboard_board(guild: discord.Guild) -> None:
    """Fetch dashboard message ID and update its statistics based on its current filter."""
    channel_id_str = database.get_setting("dashboard_channel_id", config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)
    msg_id_str = database.get_setting("dashboard_message_id", config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)

    if not channel_id_str or not msg_id_str:
        return

    try:
        channel_id = int(channel_id_str)
        msg_id = int(msg_id_str)
        channel = guild.get_channel(channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(msg_id)
        except discord.NotFound:
            return

        filter_type = "all"
        if message.embeds:
            desc = message.embeds[0].description or ""
            if "ตัวกรองช่วงเวลา: **วันนี้**" in desc:
                filter_type = "today"
            elif "ตัวกรองช่วงเวลา: **สัปดาห์นี้**" in desc:
                filter_type = "week"
            elif "ตัวกรองช่วงเวลา: **เดือนนี้**" in desc:
                filter_type = "month"

        embed = build_dashboard_embed(filter_type)
        await message.edit(embed=embed)

    except Exception as e:
        print(f"Error updating dashboard board: {e}")


def build_dashboard_embed(filter_type: str) -> discord.Embed:
    """Build statistical Discord Embed based on the time range filter."""
    stats = database.get_shifts_stats(filter_type, config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)
    top_docs = database.get_top_doctors_stats(filter_type, 10, config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)

    embed = discord.Embed(
        title="📊 แดชบอร์ดสรุปผลการเข้าเวรแพทย์ (Shift Dashboard)",
        color=discord.Color.teal(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )

    label = stats.get("label", "ทั้งหมด")
    active = stats.get("active_doctors", 0)
    hours = stats.get("total_hours", 0.0)
    shifts = stats.get("total_shifts", 0)
    unique = stats.get("unique_doctors", 0)

    desc = (
        f"📍 ตัวกรองช่วงเวลา: **{label}**\n"
        f"⏰ อัปเดตล่าสุด: <t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:f>\n\n"
        f"⚙️ **สถิติรวมในช่วงเวลาที่เลือก:**\n"
        f"• 🏥 แพทย์ที่อยู่ในเวรตอนนี้: **{active}** คน *(Global)*\n"
        f"• ⏱️ ชั่วโมงทำงานสะสมทั้งหมด: **{hours}** ชั่วโมง\n"
        f"• 📝 จำนวนเวรที่สิ้นสุดแล้ว: **{shifts}** เวร\n"
        f"• 🧑‍⚕️ แพทย์ที่เข้าเวรรวม: **{unique}** คน\n\n"
        f"🏆 **อันดับแพทย์ที่มีชั่วโมงปฏิบัติงานสูงสุด (Top 10):**\n"
    )

    if not top_docs:
        desc += "⚠️ *ยังไม่มีข้อมูลการเข้าเวรที่สมบูรณ์ในช่วงเวลานี้*"
    else:
        for idx, doc in enumerate(top_docs, 1):
            username = doc.get('username', 'Unknown')
            doc_hours = doc.get('total_hours', 0.0)
            count = doc.get('shift_count', 0)
            desc += f"**{idx}.** {username} | `{doc_hours}` ชม. ({count} เวร)\n"

    embed.description = desc
    embed.set_footer(text="ระบบวิเคราะห์ผลชั่วโมงแพทย์อัตโนมัติ")
    return embed


# --- Views & Buttons ---

def is_interaction_expired(interaction: discord.Interaction) -> bool:
    """Return True if the interaction token is older than 2.5 seconds (Discord limit is 3s)."""
    age = (datetime.datetime.now(datetime.timezone.utc) - interaction.created_at).total_seconds()
    return age > 2.5


class ShiftPanelView(discord.ui.View):
    """Persistent view containing Check-In and Check-Out buttons."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="เข้าเวร (Check In)", 
        style=discord.ButtonStyle.green, 
        custom_id="btn_check_in", 
        emoji="🏥"
    )
    async def check_in_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Skip stale interactions that have already expired (>2.5 seconds old)
        if is_interaction_expired(interaction):
            await interaction.response.send_message("⚠️ การโต้ตอบหมดอายุ กรุณากดปุ่มใหม่", ephemeral=True)
            return
        # Defer immediately to prevent 3-second timeout due to Google Sheets API latency
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)
        username = interaction.user.display_name

        try:
            check_in_time = database.start_shift(user_id, username, config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)

            # Respond to user immediately
            await interaction.followup.send(
                f"🟢 **เข้าเวรสำเร็จ!**\nลงชื่อเข้าเวรเมื่อ: `{check_in_time}`\nขอให้มีความสุขกับวันนี้นะคับ! 🏥",
                ephemeral=True
            )

            # Fire board update and log notification in the background (non-blocking)
            async def _background():
                try:
                    await asyncio.sleep(2.0)  # Delay to avoid rate limiting
                    if interaction.guild:
                        await update_all_boards(interaction.guild)
                    if config.LOG_CHANNEL_ID:
                        try:
                            log_channel = interaction.guild.get_channel(config.LOG_CHANNEL_ID)
                            if log_channel:
                                embed = discord.Embed(
                                    title="🏥 แพทย์เข้าเวร",
                                    description=f"แพทย์: {interaction.user.mention}\nเวลา: `{check_in_time}`",
                                    color=discord.Color.green(),
                                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                                )
                                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                                await log_channel.send(embed=embed)
                        except Exception as e:
                            logger.error(f"Error sending log message: {e}")
                except Exception as e:
                    logger.error(f"Background check-in task error: {e}")
            asyncio.create_task(_background())

        except ValueError as e:
            await interaction.followup.send(f"⚠️ **แจ้งเตือน:** {str(e)}", ephemeral=True)
        except Exception as e:
            print(f"Check-in error: {e}")
            await interaction.followup.send(f"❌ **เกิดข้อผิดพลาด:** {str(e)}", ephemeral=True)

    @discord.ui.button(
        label="ออกเวร (Check Out)", 
        style=discord.ButtonStyle.red, 
        custom_id="btn_check_out", 
        emoji="🏠"
    )
    async def check_out_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Skip stale interactions that have already expired (>2.5 seconds old)
        if is_interaction_expired(interaction):
            await interaction.response.send_message("⚠️ การโต้ตอบหมดอายุ กรุณากดปุ่มใหม่", ephemeral=True)
            return
        # Defer immediately to prevent 3-second timeout due to Google Sheets API latency
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)

        try:
            shift = database.end_shift(user_id, config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)
            check_in_time = shift.get("check_in")
            check_out_time = shift.get("check_out")
            duration = shift.get("duration_hours")

            # Respond to user immediately
            await interaction.followup.send(
                f"🔴 **ออกเวรสำเร็จ!**\n"
                f"เวลาเข้าเวร: `{check_in_time}`\n"
                f"เวลาออกเวร: `{check_out_time}`\n"
                f"รวมระยะเวลาทำงาน: `{duration}` ชั่วโมง\n"
                f"ขอบคุณสำหรับความเหน็ดเหนื่อยในวันนี้ครับ! 💤",
                ephemeral=True
            )

            # Fire board update and log notification in the background (non-blocking)
            async def _background():
                try:
                    await asyncio.sleep(2.0)  # Delay to avoid rate limiting
                    if interaction.guild:
                        await update_all_boards(interaction.guild)
                    if config.LOG_CHANNEL_ID:
                        try:
                            log_channel = interaction.guild.get_channel(config.LOG_CHANNEL_ID)
                            if log_channel:
                                embed = discord.Embed(
                                    title="🚪 แพทย์ออกเวร",
                                    description=f"แพทย์: {interaction.user.mention}\n"
                                                f"เวลาเข้า: `{check_in_time}`\n"
                                                f"เวลาออก: `{check_out_time}`\n"
                                                f"รวมเวลา: `{duration}` ชั่วโมง",
                                    color=discord.Color.red(),
                                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                                )
                                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                                await log_channel.send(embed=embed)
                        except Exception as e:
                            logger.error(f"Error sending log message: {e}")
                except Exception as e:
                    logger.error(f"Background check-out task error: {e}")
            asyncio.create_task(_background())

        except ValueError as e:
            await interaction.followup.send(f"⚠️ **แจ้งเตือน:** {str(e)}", ephemeral=True)
        except Exception as e:
            print(f"Check-out error: {e}")
            await interaction.followup.send(f"❌ **เกิดข้อผิดพลาด:** {str(e)}", ephemeral=True)


class DashboardSelect(discord.ui.Select):
    """Dropdown menu for selecting the time range filter on the Dashboard."""
    def __init__(self):
        options = [
            discord.SelectOption(label="วันนี้ (Today)", value="today", description="กรองข้อมูลเฉพาะวันนี้", emoji="📅"),
            discord.SelectOption(label="สัปดาห์นี้ (Week)", value="week", description="กรองข้อมูลสัปดาห์นี้", emoji="📆"),
            discord.SelectOption(label="เดือนนี้ (Month)", value="month", description="กรองข้อมูลเดือนนี้", emoji="🗓️"),
            discord.SelectOption(label="ทั้งหมด (All Time)", value="all", description="แสดงข้อมูลทั้งหมด", emoji="📊", default=True)
        ]
        super().__init__(
            custom_id="select_dashboard_filter",
            placeholder="เลือกช่วงเวลาเพื่อกรองข้อมูล...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # Skip stale interactions that have already expired
        if is_interaction_expired(interaction):
            return
        # Defer first to avoid 3-second interaction timeout from Google Sheets API latency
        await interaction.response.defer()

        filter_type = self.values[0]

        # Update dropdown default state
        for option in self.options:
            option.default = (option.value == filter_type)

        embed = build_dashboard_embed(filter_type)
        # Use edit_original_response after deferring
        await interaction.edit_original_response(embed=embed, view=self.view)


class DashboardView(discord.ui.View):
    """Persistent view for the Dashboard containing filter dropdown, refresh, and CSV export."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(DashboardSelect())

    @discord.ui.button(
        label="รีเฟรชสถิติ (Refresh)", 
        style=discord.ButtonStyle.primary, 
        custom_id="btn_refresh_dashboard", 
        emoji="🔄",
        row=1
    )
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Skip stale interactions that have already expired
        if is_interaction_expired(interaction):
            return
        # Defer immediately to prevent timeout during Google Sheets API call
        await interaction.response.defer()

        select_menu = [item for item in self.children if isinstance(item, DashboardSelect)][0]
        selected_value = "all"
        for opt in select_menu.options:
            if opt.default:
                selected_value = opt.value
                break

        embed = build_dashboard_embed(selected_value)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(
        label="ดาวน์โหลด CSV", 
        style=discord.ButtonStyle.secondary, 
        custom_id="btn_download_csv_dashboard", 
        emoji="📊",
        row=1
    )
    async def csv_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⚠️ ขออภัย เฉพาะผู้ดูแลระบบ (Administrator) เท่านั้นที่ดาวน์โหลดได้",
                ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        select_menu = [item for item in self.children if isinstance(item, DashboardSelect)][0]
        selected_value = "all"
        for opt in select_menu.options:
            if opt.default:
                selected_value = opt.value
                break

        try:
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temp_file:
                temp_path = temp_file.name

            database.export_shifts_to_csv_by_filter(selected_value, config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH, temp_path)

            th_label = "ทั้งหมด"
            if selected_value == "today": th_label = "วันนี้"
            elif selected_value == "week": th_label = "สัปดาห์นี้"
            elif selected_value == "month": th_label = "เดือนนี้"

            file_to_send = discord.File(temp_path, filename=f"shifts_{selected_value}_{datetime.date.today()}.csv")
            await interaction.followup.send(
                content=f"📊 **รายงานประวัติเข้า��วรแพทย์ (ตัวกรอง: {th_label})** ถูกจัดส่งเรียบร้อยแล้ว!",
                file=file_to_send,
                ephemeral=True
            )
            os.remove(temp_path)
        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการดึงรายงาน: {str(e)}", ephemeral=True)


# --- Bot Initialization ---

class ShiftBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, reconnect=True)

    async def setup_hook(self):
        self.add_view(ShiftPanelView())
        self.add_view(DashboardView())

        # Verify Sheet parameters
        if not config.GOOGLE_SHEET_ID or config.GOOGLE_SHEET_ID == "your_google_sheet_id_here":
            print("WARNING: GOOGLE_SHEET_ID is not set! Google Sheets database operations will fail.")
        else:
            try:
                database.init_db(config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)
                print(f"Google Sheet database initialized.")
            except Exception as e:
                print(f"ERROR: Failed to initialize Google Sheets database: {e}")

        # Sync commands
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Synced slash commands to server: {config.GUILD_ID}")
        else:
            await self.tree.sync()
            print("Synced slash commands globally")

    async def on_ready(self):
        logger.info(f"Bot logged in as {self.user.name} ({self.user.id})")
        if not self.background_keep_alive.is_running():
            self.background_keep_alive.start()
        if not self.periodic_board_update.is_running():
            self.periodic_board_update.start()
        if config.GOOGLE_SHEET_ID and config.GOOGLE_SHEET_ID != "your_google_sheet_id_here":
            for guild in self.guilds:
                try:
                    await update_all_boards(guild)
                except Exception as e:
                    logger.warning(f"Could not update boards on startup: {e}")

    async def on_error(self, event_method: str, *args, **kwargs):
        logger.error(f"Unhandled error in {event_method}", exc_info=True)

    async def on_socket_raw_receive(self, msg):
        pass  # keep event loop alive

    @tasks.loop(minutes=2)
    async def background_keep_alive(self):
        """Periodically ping the keep-alive server to prevent Render from sleeping."""
        try:
            import urllib.request
            port = int(os.environ.get("PORT", 8080))
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5)
        except Exception:
            pass

    @background_keep_alive.before_loop
    async def before_keep_alive(self):
        await self.wait_until_ready()

    @tasks.loop(minutes=5)
    async def periodic_board_update(self):
        """Periodically update boards to keep activity and prevent sleeping."""
        if not self.is_ready():
            return
        for guild in self.guilds:
            try:
                await update_all_boards(guild)
            except Exception as e:
                logger.warning(f"Periodic board update failed: {e}")

    @periodic_board_update.before_loop
    async def before_periodic_update(self):
        await self.wait_until_ready()

bot = ShiftBot()


# --- Slash Commands ---

@bot.tree.command(name="setup", description="ติดตั้งปุ่มกดเข้าเวร-ออกเวร และบอร์ดรายชื่อคนเข้าเวร")
@app_commands.checks.has_permissions(administrator=True)
async def setup_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    panel_embed = discord.Embed(
        title="🩺 ระบบลงเวลากลุ่มแพทย์ปฏิบัติงาน (Shift Logs)",
        description="กรุณากดปุ่มด้านล่างเพื่อลงเวลาทำงานของท่าน\n\n"
                    "🟢 **เข้าเวร (Check In)**: บันทึกเวลาเริ่มต้นทำงานในเวร\n"
                    "🔴 **ออกเวร (Check Out)**: บันทึกเวลาเลิกงานและคำนวณชั่วโมง\n\n"
                    "*ประวัติและชั่วโมงการทำงานทั้งหมดจะถูกจัดเก็บลงฐานข้อมูลอัตโนมัติ*",
        color=discord.Color.blue()
    )
    panel_embed.set_footer(text="ระบบบันทึกเวลาเวรแพทย์อัตโนมัติ")
    await interaction.channel.send(embed=panel_embed, view=ShiftPanelView())

    active_embed = discord.Embed(
        title="🏥 รายชื่อแพทย์ที่กำลังปฏิบัติงานอยู่ในเวร (Active Doctors)",
        description="❌ ขณะนี้ไม่มีแพทย์ปฏิบัติงานในเวร\n\n*(แพทย์สามารถเข้าเวรได้โดยกดปุ่ม \"เข้าเวร\")*",
        color=discord.Color.light_grey()
    )
    active_embed.set_footer(text="อัปเดตอัตโนมัติเรียลไทม์")
    status_message = await interaction.channel.send(embed=active_embed)

    database.set_setting("active_status_channel_id", str(interaction.channel_id), config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)
    database.set_setting("active_status_message_id", str(status_message.id), config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)

    await update_active_duty_board(interaction.guild)

    await interaction.followup.send(
        "✅ **ติดตั้งเสร็จสิ้น!**\n"
        "• สร้างแผงปุ่มกด และสร้างบอร์ดแสดงรายชื่อคนเข้าเวรเรียบร้อยแล้ว\n"
        "• บอร์ดจะทำการอัปเดตรายชื่ออัตโนมัติเมื่อแพทย์ทำการเข้า-ออกเวร",
        ephemeral=True
    )


@setup_panel.error
async def setup_panel_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("⚠️ ขออภัย คุณจำเป็นต้องมีสิทธิ์เป็น `Administrator` เพื่อรันคำสั่งนี้",
            ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(error)}", ephemeral=True)


@bot.tree.command(name="setup-dashboard", description="ติดตั้งแดชบอร์ดสรุปสถิติเวรสะสมแบบกรองได้ (สำหรับ Admin)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_dashboard(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    embed = build_dashboard_embed("all")
    dashboard_message = await interaction.channel.send(embed=embed, view=DashboardView())

    database.set_setting("dashboard_channel_id", str(interaction.channel_id), config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)
    database.set_setting("dashboard_message_id", str(dashboard_message.id), config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)

    await interaction.followup.send(
        "✅ **ติดตั้งแดชบอร์ดสรุปสถิติสำเร็จ!**\n"
        "• แดชบอร์ดนี้สามารถกรองเวลาดูย้อนหลังได้โดยตรงทางแชท\n"
        "• ปุ่มดาวน์โหลดจะดึงไฟล์ Excel (CSV) ตามตัวเลือกที่เลือก",
        ephemeral=True
    )


@setup_dashboard.error
async def setup_dashboard_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("⚠️ ขออภัย คุณจำเป็นต้องมีสิทธิ์เป็น `Administrator` เพื่อรันคำสั่งนี้",
            ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {str(error)}", ephemeral=True)


@bot.tree.command(name="status", description="ตรวจสอบรายชื่อแพทย์ที่กำลังปฏิบัติงานอยู่ในเวรขณะนี้")
async def view_status(interaction: discord.Interaction):
    active_shifts = database.get_currently_on_duty(config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)

    if not active_shifts:
        embed = discord.Embed(
            title="🏥 แพทย์ที่กำลังอยู่ในเวร",
            description="❌ ไม่มีแพทย์กำลังปฏิบัติหน้าที่อยู่ในเวรขณะนี้",
            color=discord.Color.light_grey()
        )
        await interaction.response.send_message(embed=embed)
        return

    embed = discord.Embed(
        title="🏥 แพทย์ที่กำลังปฏิบัติงานอยู่ในเวรขณะนี้",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    
    list_content = ""
    now_local = datetime.datetime.now(LOCAL_TZ)
    for idx, shift in enumerate(active_shifts, 1):
        user_id = shift.get('user_id')
        username = shift.get('username')
        check_in_str = shift.get('check_in') or ""
        
        check_in_dt = parse_sheet_time_to_local(check_in_str)
        if check_in_dt is None:
            time_elapsed = "ไม่ทราบระยะเวลา"
        else:
            diff = now_local - check_in_dt
            if diff.total_seconds() < 0:
                diff = datetime.timedelta(0)
            hours, remainder = divmod(int(diff.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            time_elapsed = f"{hours} ชม. {minutes} นาที {seconds} วินาที"
            
        list_content += f"{idx}. <@{user_id}> (ชื่อในระบบ: {username})\n   ⏱️ เข้าเวรเมื่อ: `{check_in_str}` (ทำมาแล้ว: `{time_elapsed}`)\n\n"
        
    embed.description = list_content
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="my-shifts", description="ดูประวัติการเข้าเวรล่าสุดและชั่วโมงทำงานสะสมของคุณ")
async def my_shifts(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    history = database.get_user_history(user_id, 5, config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)
    total_hours = database.get_user_total_hours(user_id, config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)
    
    embed = discord.Embed(
        title=f"📊 สรุปเวลางานของคุณ: {interaction.user.display_name}",
        color=discord.Color.teal()
    )
    embed.add_field(name="⏱️ ชั่วโมงสะสมรวม (เฉพาะที่ออกเวรแล้ว)", value=f"`{total_hours}` ชั่วโมง", inline=False)
    
    if not history:
        embed.description = "📝 ไม่พบประวัติการเข้าเวรของคุณในระบบ"
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    history_text = "**ประวัติ 5 เวรล่าสุด:**\n"
    for shift in history:
        check_in = shift.get('check_in')
        check_out = shift.get('check_out') if shift.get('check_out') else "*กำลังเข้าเวรอยู่*"
        duration = f"{shift.get('duration_hours')} ชั่วโมง" if shift.get('duration_hours') is not None else "-"
        
        history_text += f"• **เข้า:** `{check_in}` | **ออก:** `{check_out}` | **รวม:** `{duration}`\n"
        
    embed.description = history_text
    await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    if not config.DISCORD_TOKEN or config.DISCORD_TOKEN == "your_discord_bot_token_here":
        print("ERROR: Please set your DISCORD_TOKEN in the .env file!")
    else:
        # Start keep-alive web server to satisfy Render's port binding check
        keep_alive()
        
        # Start Discord Bot
        bot.run(config.DISCORD_TOKEN)
