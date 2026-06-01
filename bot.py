import sys
import subprocess

# ====================================================================
# AUTO-INSTALLER GUARD (Mencegah Crash ModuleNotFoundError di Railway)
# ====================================================================
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ModuleNotFoundError:
    print("Mendapati 'apscheduler' belum terpasang. Menginstal secara otomatis...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "apscheduler==3.10.4"])
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Inisialisasi scheduler setelah dipastikan modulnya terinstal
scheduler = AsyncIOScheduler()

# ====================================================================
# CONFIGURATION
# ====================================================================
ID_CHANNEL_LOG_LOA = 1510642659776266442  # ID Channel Admin kamu
ID_ROLE_LOA = 1469270847905730590         # ID Role LOA kamu
GUILD_ID = 1351182942625337378            # ID Server (Guild) kamu
DATA_FILE = "loa_data.json"

# ID Khusus untuk Fitur Pengumuman Session Roleplay
ID_ROLE_PEMERINTAH = 1508831415461220423  # Tag Pemerintah
ID_CHANNEL_ANNOUNCEMENT = 1351182942625337378 # ID channel tempat pengumuman jadwal dikirim

# Role yang diizinkan menggunakan !setsession
ALLOWED_ROLE_SESSION_IDS = [
    1508831415461220423, # Role Pemerintah
    1351203409692463135, # ID Role Staf Tambahan 1
    1434199488398102688  # ID Role Staf Tambahan 2
]

# ====================================================================
# SAKELAR SISTEM LOA (GLOBAL STATE)
# ====================================================================
loa_system_active = True

# ====================================================================
# DATABASE FUNCTIONS
# ====================================================================
def load_loa_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_loa_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ====================================================================
# AUTOMATIC CHECKER TASK (RUNS EVERY HOUR)
# ====================================================================
@tasks.loop(hours=1.0)
async def check_expired_loa():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    role_loa = guild.get_role(ID_ROLE_LOA)
    if not role_loa:
        return

    loa_data = load_loa_data()
    now = datetime.now()
    updated = False

    for member_id_str, details in list(loa_data.items()):
        try:
            end_date = datetime.strptime(details["end_date"], "%d/%m/%Y")
            if now.date() > end_date.date():
                member_id = int(member_id_str)
                member = guild.get_member(member_id)
                
                if member and role_loa in member.roles:
                    try:
                        await member.remove_roles(role_loa)
                        embed_dm = discord.Embed(
                            title="Notice of LOA Termination",
                            description=f"Hello {member.mention},\n\nThis is an official automated notification to inform you that your Leave of Absence (LOA) period has concluded. Your LOA role has been removed, and you are expected to resume your standard duties and responsibilities.",
                            color=discord.Color(0x0d50b8)
                        )
                        embed_dm.set_footer(text="Thank you for your cooperation and welcome back.")
                        await member.send(embed=embed_dm)
                    except Exception as e:
                        print(f"Failed to remove role or DM member {member_id}: {e}")
                
                log_channel = bot.get_channel(ID_CHANNEL_LOG_LOA)
                if log_channel:
                    await log_channel.send(f"Automated System: LOA period has concluded for <@{member_id_str}>. Role removed.")

                del loa_data[member_id_str]
                updated = True
        except ValueError:
            continue

    if updated:
        save_loa_data(loa_data)

# ====================================================================
# MODAL: REJECTION REASON FOR ADMIN
# ====================================================================
class RejectReasonModal(discord.ui.Modal, title="LOA Rejection Reason"):
    reason = discord.ui.TextInput(
        label="Reason for Rejection",
        style=discord.TextStyle.long,
        placeholder="Provide a clear explanation why this LOA request was rejected...",
        required=True,
        max_length=300
    )

    def __init__(self, member_id: int, interaction_admin: discord.Interaction, view_approval):
        super().__init__()
        self.member_id = member_id
        self.interaction_admin = interaction_admin
        self.view_approval = view_approval

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        member = await bot.fetch_user(self.member_id)
        
        embed = self.interaction_admin.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "LOA REQUEST - REJECTED"
        embed.add_field(name="Reason for Rejection", value=self.reason.value, inline=False)
        embed.set_footer(text=f"Rejected by: {interaction.user.name}")
        
        await self.interaction_admin.message.edit(embed=embed, view=self.view_approval)

        if member:
            try:
                embed_dm = discord.Embed(
                    title="Your LOA Request Has Been Rejected",
                    description=f"Hello {member.mention},\n\nWe regret to inform you that your Leave of Absence (LOA) request has been reviewed and rejected by the administration.",
                    color=discord.Color.red()
                )
                embed_dm.add_field(name="Reason for Rejection", value=self.reason.value, inline=False)
                embed_dm.set_footer(text="Please contact the President or Vice President for further clarification.")
                await member.send(embed=embed_dm)
            except discord.Forbidden:
                pass

# ====================================================================
# VIEW: APPROVAL BUTTONS FOR ADMIN
# ====================================================================
class AdminApprovalView(discord.ui.View):
    def __init__(self, member_id: int, data_form: dict):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.data_form = data_form

    @discord.ui.button(label="Accept Request", style=discord.ButtonStyle.success, custom_id="approve_loa")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild = interaction.guild
        member = guild.get_member(self.member_id)
        
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.title = "LOA REQUEST - APPROVED"
        embed.set_footer(text=f"Approved by: {interaction.user.name}")
        
        for child in self.children:
            child.disabled = True
            
        await interaction.message.edit(embed=embed, view=self)

        if member:
            role_loa = guild.get_role(ID_ROLE_LOA)
            if role_loa:
                try:
                    await member.add_roles(role_loa)
                except discord.Forbidden:
                    print("Bot lacks permissions to assign the role.")
            
            loa_data = load_loa_data()
            loa_data[str(self.member_id)] = {
                "username": self.data_form["username"],
                "end_date": self.data_form["end_date"]
            }
            save_loa_data(loa_data)

            try:
                embed_dm = discord.Embed(
                    title="Your LOA Request Has Been Approved",
                    description=f"Hello {member.mention},\n\nYour Leave of Absence (LOA) request has been successfully reviewed and approved by the administration.",
                    color=discord.Color.green()
                )
                embed_dm.add_field(name="End Date", value=self.data_form['end_date'], inline=False)
                embed_dm.set_footer(text="The Leave of Absence role has been assigned. System will auto-remove it once concluded.")
                await member.send(embed=embed_dm)
            except discord.Forbidden:
                pass

    @discord.ui.button(label="Reject Request", style=discord.ButtonStyle.danger, custom_id="reject_loa")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        modal_reject = RejectReasonModal(member_id=self.member_id, interaction_admin=interaction, view_approval=self)
        await interaction.response.send_modal(modal_reject)

# ====================================================================
# MODAL: FORMULIR LOA
# ====================================================================
class LOAForm(discord.ui.Modal, title="Leave of Absence Application"):
    q1 = discord.ui.TextInput(label="1. Roblox Username", placeholder="Enter your full Roblox username...", required=True, max_length=50)
    q2 = discord.ui.TextInput(label="2. Position / Department", placeholder="Your current position, rank, or department...", required=True, max_length=70)
    q3 = discord.ui.TextInput(label="3. LOA End Date Only (Format: DD/MM/YYYY)", placeholder="Example: 15/06/2026", required=True, max_length=15)
    q4 = discord.ui.TextInput(label="4. Reason & Notes", style=discord.TextStyle.long, placeholder="Provide a clear explanation for your absence...", required=True, max_length=400)
    q5 = discord.ui.TextInput(label="5. Reachable during leave? (Yes / No)", placeholder="Can you be contacted via Discord if urgent? Yes / No", required=True, max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user
        await interaction.response.defer(ephemeral=True)
        
        input_date = self.q3.value.strip()
        try:
            datetime.strptime(input_date, "%d/%m/%Y")
        except ValueError:
            await interaction.followup.send("Submission failed! Invalid date format. Please use DD/MM/YYYY (e.g., 07/06/2026).", ephemeral=True)
            return

        data_form = {
            "username": self.q1.value,
            "end_date": input_date
        }
        
        embed = discord.Embed(
            title="PENDING LOA REQUEST",
            description=f"A new submission has been received from {member.mention}",
            color=discord.Color.orange()
        )
        embed.add_field(name="Roblox Username", value=self.q1.value, inline=True)
        embed.add_field(name="Department / Position", value=self.q2.value, inline=True)
        embed.add_field(name="End Date (Auto-Expiry)", value=self.q3.value, inline=False)
        embed.add_field(name="Reason for Leave", value=self.q4.value, inline=False)
        embed.add_field(name="Reachable Status", value=self.q5.value, inline=False)
        
        log_channel = bot.get_channel(ID_CHANNEL_LOG_LOA)
        if log_channel:
            view_admin = AdminApprovalView(member_id=member.id, data_form=data_form)
            await log_channel.send(embed=embed, view=view_admin)
            await interaction.followup.send("Your LOA request has been securely submitted. The outcome will be delivered directly to your DM once reviewed.", ephemeral=True)
        else:
            await interaction.followup.send("Error: Log channel not found.", ephemeral=True)

class LOAButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create LOA", style=discord.ButtonStyle.secondary, custom_id="button_create_loa")
    async def create_loa_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not loa_system_active:
            return await interaction.response.send_message(
                "We regret to inform you that you are unable to submit a Leave of Absence (LOA) request at this time, "
                "as the LOA system has been temporarily disabled by the Executive Directorate. Kindly wait until the "
                "system is reactivated before submitting your request. Thank you for your understanding.", 
                ephemeral=True
            )
        await interaction.response.send_modal(LOAForm())

# ====================================================================
# AUTOMATED ROLEPLAY SESSION PLANNER
# ====================================================================
async def send_automated_server_code(channel_id, server_code, location_rp):
    channel = bot.get_channel(channel_id)
    if channel:
        msg = (
            f"**Code Server:** `{server_code}`\n"
            f"**Location / Venue:** {location_rp}\n"
            f"<@&{ID_ROLE_PEMERINTAH}> | @everyone"
        )
        await channel.send(msg)

class SessionPlannerModal(discord.ui.Modal, title="Create Roleplay Session"):
    day_date = discord.ui.TextInput(label="Day & Date Session", placeholder="Example: Tuesday, 26 May 2026", required=True)
    time_schedule = discord.ui.TextInput(
        label="Schedules (Staff Join, Open, STS, Start)", 
        style=discord.TextStyle.long,
        placeholder="Staff join : 20.30\nOpen Server : 21.00\nSTS : 21.05\nRoleplay start : 21.10", 
        required=True
    )
    staff_join_time = discord.ui.TextInput(
        label="Exact Staff Join Time (For Auto-Code Bot)", 
        placeholder="Format HH.MM (Example: 20.30)", 
        max_length=5, 
        required=True
    )
    server_code = discord.ui.TextInput(label="Server Code (Kept secret until staff join)", placeholder="Enter Roblox server code/link...", required=True)
    location_rp = discord.ui.TextInput(label="AORP / Venue Roleplay Place", placeholder="Example: Gedung DPR-RI / Map Room A", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        time_str = self.staff_join_time.value.strip().replace(":", ".")
        try:
            hour, minute = map(int, time_str.split('.'))
        except ValueError:
            await interaction.followup.send("❌ Setup Failed! Staff Join time format must be HH.MM or HH:MM (e.g., 20.30)", ephemeral=True)
            return

        announcement_text = (
            f"**__Rise Country__**\n\n"
            f"**<@&{ID_ROLE_PEMERINTAH}>**\n"
            f"{self.day_date.value} at {hour:02d}.{minute:02d}\n"
            f"<@&{ID_ROLE_PEMERINTAH}> | @everyone\n\n"
            f"**__Schedule__**\n\n"
            f"{self.time_schedule.value}\n"
            f"• End session : Estimated at 11:00 pm or 12:00 pm (depending on the situation)\n"
            f"Session time : {hour:02d}.{minute:02d} - Selesai (GMT +7)\n\n"
            f"Note :\n"
            f"• Minimum requirement: 5 staff\n"
            f"• Please join at the scheduled time.\n"
            f"• The schedule may change at any time."
        )

        announcement_channel = bot.get_channel(ID_CHANNEL_ANNOUNCEMENT)
        if announcement_channel:
            await announcement_channel.send(announcement_text)
            
            scheduler.add_job(
                send_automated_server_code,
                'cron',
                hour=hour,
                minute=minute,
                args=[ID_CHANNEL_ANNOUNCEMENT, self.server_code.value, self.location_rp.value],
                id=f"session_job_{interaction.id}"
            )
            
            await interaction.followup.send(
                f"✅ Session successfully scheduled! The schedule announcement has been posted. "
                f"The bot will automatically release the Server Code at {hour:02d}.{minute:02d} sharp.", 
                ephemeral=True
            )
        else:
            await interaction.followup.send("❌ Error: Target announcement channel not found.", ephemeral=True)

@bot.command(name="setsession")
async def start_session_planner(ctx):
    user_roles = [role.id for role in ctx.author.roles]
    has_permission = ctx.author.guild_permissions.administrator or any(role_id in user_roles for role_id in ALLOWED_ROLE_SESSION_IDS)
    
    if not has_permission:
        return  # SILENT: Bot diam saja tanpa merespons jika bukan admin/staf berizin

    modal_session = SessionPlannerModal()
    class TriggerView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
        @discord.ui.button(label="Click to Open Session Form", style=discord.ButtonStyle.primary)
        async def open_form(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("This setup belongs to someone else.", ephemeral=True)
            await interaction.response.send_modal(modal_session)
            self.stop()

    await ctx.send("Click the button below to fill out the session schedule:", view=TriggerView(), delete_after=60)

# ====================================================================
# COMMAND: KENDALI SISTEM SAKELAR LOA (KHUSUS ADMIN)
# ====================================================================
@bot.command(name="loasystem")
@commands.has_permissions(administrator=True)
async def toggle_loa_system(ctx, status: str = None):
    global loa_system_active

    if status is None:
        current_status = "ENABLED" if loa_system_active else "DISABLED"
        return await ctx.send(
            f"⚙️ **LOA System Status:** `{current_status}`\n"
            f"Use `!loasystem off` to disable or `!loasystem on` to enable the portal."
        )

    if status.lower() == "off":
        loa_system_active = False
        await ctx.send("The Leave of Absence (LOA) system has been temporarily disabled. Please await further notice regarding its reactivation.")
    elif status.lower() == "on":
        loa_system_active = True
        await ctx.send("The Leave of Absence (LOA) system has been reactivated and is now available for use. Eligible members may proceed with submitting their LOA requests in accordance with the established procedures.")
    else:
        await ctx.send("❌ Invalid format. Use `!loasystem on` or `!loasystem off`.")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_loa(ctx):
    desc_text = (
        "Welcome to the Leave of Absence System.\n\n"
        "This system is intended for members who require a temporary leave from their duties and responsibilities. "
        "Please submit your request with a clear reason and an accurate duration of absence.\n\n"
        "All submissions will be reviewed by the President or Vice President. Requests containing false information "
        "or any misuse of this system may result in disciplinary action in accordance with applicable regulations.\n\n"
        "The outcome of your LOA request will be sent to you via Direct Message (DM) once it has been reviewed and approved "
        "by the President or Vice President.\n\n"
        "Thank you for your cooperation and professionalism."
    )
    embed = discord.Embed(title="Leave of Absence (LOA) Portal", description=desc_text, color=discord.Color(0x0d50b8))
    await ctx.send(embed=embed, view=LOAButtonView())

@bot.command()
@commands.has_permissions(administrator=True)
async def end_loa(ctx, member: discord.Member):
    role_loa = ctx.guild.get_role(ID_ROLE_LOA)
    if role_loa in member.roles:
        await member.remove_roles(role_loa)
        loa_data = load_loa_data()
        if str(member.id) in loa_data:
            del loa_data[str(member.id)]
            save_loa_data(loa_data)
        await ctx.send(f"LOA manually terminated for {member.display_name}.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        return  # SILENT
    raise error

# ====================================================================
# MAIN APPLICATION EVENTS
# ====================================================================
@bot.event
async def on_ready():
    bot.add_view(LOAButtonView())
    if not check_expired_loa.is_running():
        check_expired_loa.start()
    
    if not scheduler.running:
        scheduler.start()
        
    print(f"System Active! {bot.user} is fully automated.")

bot.run(os.getenv('DISCORD_TOKEN'))
