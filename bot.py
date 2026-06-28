import discord
from discord import app_commands
from discord.ext import commands
import os
import datetime
from zoneinfo import ZoneInfo
import tempfile
import config
import database
from flask import Flask
import threading

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
    datetime in LOCAL_TZ. Logic:
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
            embed.description = "❌ ขณะนี้ไม่มีแพทย์ปฏิบัติงานในเวร\n\n*(แพทย์สามารถเข้าเวรได้โดยกดปุ่ม \"เข้าเวร\")*"
            embed.color = discord.Color.light_grey()
        else:
            description_text = "⏱️ **กำลังปฏิบัติงาน:**\n\n"
            now_local = datetime.datetime.now(LOCAL_TZ)
            for idx, shift in enumerate(active_shifts, 1):
                user_id = shift.get('user_id')
                check_in_str = shift.get('check_in') or ""

                try:
                    check_in_dt = parse_sheet_time_to_local(check_in_str)
                    if check_in_dt is None:
                        raise ValueError("parse error")
                    diff = now_local - check_in_dt
                    # Clamp negative diffs to zero to avoid showing negative hours
                    if diff.total_seconds() < 0:
                        diff = datetime.timedelta(0)
                    hours, remainder = divmod(int(diff.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    time_elapsed = f"{hours} ชม. {minutes} นาที {seconds} วินาที"
                except Exception:
                    time_elapsed = "ไม่ทราบระยะเวลา"

                description_text += f"{idx}. <@{user_id}> \n   ⏱️ เข้าเวรเมื่อ: `{check_in_str}` (อยู่ในเวรมาแล้ว: `{time_elapsed}`)\n\n"
            embed.description = description_text

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


async def update_all_boards(guild: discord.Guild) -> None:
    """Update both status and statistics boards."""
    await update_active_duty_board(guild)
    await update_dashboard_board(guild)


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
            return
        # Defer immediately to prevent 3-second timeout due to Google Sheets API latency
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)
        username = interaction.user.display_name

        try:
            check_in_time = database.start_shift(user_id, username, config.GOOGLE_SHEET_ID, config.CREDENTIALS_JSON_PATH)

            # Respond to user immediately
            await interaction.followup.send(
                f"🟢 **เข้าเวรสำเร็จ!**\nลงชื่อเข้าเวรเมื่อ: `{check_in_time}`\nขอให้มีความสุขกับการทำงานในวันนี้ครับ! 💪",
                ephemeral=True
            )

            # Fire board update and log notification in the background (non-blocking)
            async def _background():
                if interaction.guild:
                    await update_all_boards(interaction.guild)
                if config.LOG_CHANNEL_ID:
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
            import asyncio
            asyncio.create_task(_background())

        except ValueError as e:
            await interaction.followup.send(f"⚠️ **แจ้งเตือน:** {str(e)}", ephemeral=True)
        except Exception as e:
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
                if interaction.guild:
                    await update_all_boards(interaction.guild)
                if config.LOG_CHANNEL_ID:
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
            import asyncio
            asyncio.create_task(_background())

        except ValueError as e:
            await interaction.followup.send(f"⚠️ **แจ้งเตือน:** {str(e)}", ephemeral=True)
        except Exception as e:
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
            await interaction.response.send_message("⚠️ ขออภัย เฉพาะผู้ดูแลระบบ (Administrator) เท่านั้นที่ดาวน์โ[...]", ephemeral=True)
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
                content=f"📊 **รายงานประวัติเข้าเวรแพทย์ (ตัวกรอง: {th_label})** ถูกจัดส่งเรียบร้[...]",
                file=file_to_send,
                ephemeral=True
            )
            os.remove(temp_path)
        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการดึงรายงาน: {str(e)}", ephemeral=True)


# --- Bot Initialization ---

The content truncated due to size. I'll stop here.