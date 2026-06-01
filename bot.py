import sys
import subprocess

# ====================================================================
# AUTO-INSTALLER GUARD
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
scheduler = AsyncIOScheduler()

# ====================================================================
# CONFIGURATION
# ====================================================================
ID_CHANNEL_LOG_LOA = 1510642659776266442  
ID_ROLE_LOA = 1469270847905730590         
GUILD_ID = 1351182942625337378            
DATA_FILE = "loa_data.json"

ID_CHANNEL_ANNOUNCEMENT = 1400173631421546620 

SERVER_CHANNELS = {
    "1": 1351207506612846638,
    "2": 1351210046599462945,
    "3": 1469229327219425334
}

ALLOWED_ROLE_SESSION_IDS = [
    1508831415461220423, 
    1351203409692463135, 
    1434199488398102688  
]

loa_system_active = True
session_storage = {}  # Penyimpanan sementara data form antar-halaman

# ====================================================================
# DATABASE FUNCTIONS
# ====================================================================
def load_loa_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {}
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
    if not guild: return
    role_loa = guild.get_role(ID_ROLE_LOA)
    if not role_loa: return
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
                        embed_dm = discord.Embed(title="Notice of LOA Termination", color=discord.Color(0x0d50b8))
                        await member.send(embed=embed_dm)
                    except Exception: pass
                del loa_data[member_id_str]
                updated = True
        except ValueError: continue
    if updated: save_loa_data(loa_data)

# ====================================================================
# LOA COMPONENTS
# ====================================================================
class RejectReasonModal(discord.ui.Modal, title="LOA Rejection Reason"):
    reason = discord.ui.TextInput(label="Reason for Rejection", style=discord.TextStyle.long, required=True, max_length=300)
    def __init__(self, member_id: int, interaction_admin: discord.Interaction, view_approval):
        super().__init__()
        self.member_id = member_id
        self.interaction_admin = interaction_admin
        self.view_approval = view_approval
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = self.interaction_admin.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "LOA REQUEST - REJECTED"
        embed.add_field(name="Reason for Rejection", value=self.reason.value, inline=False)
        await self.interaction_admin.message.edit(embed=embed, view=self.view_approval)

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
        for child in self.children: child.disabled = True
        await interaction.message.edit(embed=embed, view=self)
        if member:
            role_loa = guild.get_role(ID_ROLE_LOA)
            if role_loa:
                try: await member.add_roles(role_loa)
                except discord.Forbidden: pass
            loa_data = load_loa_data()
            loa_data[str(self.member_id)] = {"username": self.data_form["username"], "end_date": self.data_form["end_date"]}
            save_loa_data(loa_data)

    @discord.ui.button(label="Reject Request", style=discord.ButtonStyle.danger, custom_id="reject_loa")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children: child.disabled = True
        await interaction.response.send_modal(RejectReasonModal(member_id=self.member_id, interaction_admin=interaction, view_approval=self))

class LOAForm(discord.ui.Modal, title="Leave of Absence Application"):
    q1 = discord.ui.TextInput(label="1. Roblox Username", required=True, max_length=50)
    q2 = discord.ui.TextInput(label="2. Position / Department", required=True, max_length=70)
    q3 = discord.ui.TextInput(label="3. LOA End Date Only (Format: DD/MM/YYYY)", required=True, max_length=15)
    q4 = discord.ui.TextInput(label="4. Reason & Notes", style=discord.TextStyle.long, required=True, max_length=400)
    q5 = discord.ui.TextInput(label="5. Reachable during leave? (Yes / No)", required=True, max_length=10)
    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user
        await interaction.response.defer(ephemeral=True)
        try: datetime.strptime(self.q3.value.strip(), "%d/%m/%Y")
        except ValueError:
            await interaction.followup.send("Submission failed! Invalid date format.", ephemeral=True)
            return
        log_channel = bot.get_channel(ID_CHANNEL_LOG_LOA)
        if log_channel:
            embed = discord.Embed(title="PENDING LOA REQUEST", description=f"Submission from {member.mention}", color=discord.Color.orange())
            await log_channel.send(embed=embed, view=AdminApprovalView(member_id=member.id, data_form={"username": self.q1.value, "end_date": self.q3.value}))
            await interaction.followup.send("Your LOA request has been securely submitted.", ephemeral=True)

class LOAButtonView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Create LOA", style=discord.ButtonStyle.secondary, custom_id="button_create_loa")
    async def create_loa_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not loa_system_active: return await interaction.response.send_message("The LOA system has been temporarily disabled.", ephemeral=True)
        await interaction.response.send_modal(LOAForm())


# ====================================================================
# FIX: REWORKED INTERACTIVE MULTI-PAGE ROLEPLAY PLANNER
# ====================================================================

async def send_automated_strict_rp_template(target_channel_id, host_name, map_author, aorp_loc, server_code):
    channel = bot.get_channel(target_channel_id)
    if channel:
        template = (
            f"# **RiseCountry 🔴 STRICT RP**\n"
            f"**AORP : {aorp_loc}**\n"
            f"--------------------\n"
            f"Host : {host_name}\n"
            f"Moderator : Staff RCRP\n"
            f"Map by : {map_author}\n"
            f"--------------------\n"
            f"**SERVICE CALL**\n"
            f"**911** POLISI\n"
            f"**119** AMBULAN\n"
            f"**112** PEMADAM\n"
            f"--------------------\n"
            f"**JOBS**\n"
            f"- Sopir Taxi\n"
            f"- Sopir Bus\n"
            f"- Sopir Truk\n"
            f"- Teknisi Bengkel\n"
            f"- Pedagang\n"
            f"- DLL\n"
            f"--------------------\n"
            f"**BANNED CARS**\n"
            f"- Strobo & Emergency  [Host and Staff only]\n"
            f"- Mobil Diatas 5M\n"
            f"- Limited (Selain Mobil In-House/Officially Tuned, Contoh: Brabus, Gemballa, Nismo, Ruf, etc)\n"
            f"--------------------\n"
            f"**ROLEPLAY RULES**\n"
            f"- Memakai Sein\n"
            f"- Menabrak Wajib \"Exc\"\n"
            f"- Mengikuti Rambu Lalu Lintas\n"
            f"- Auto Flip Car OFF\n"
            f"- Kunci Kendaraan\n"
            f"- PvP ON\n"
            f"- LOR Allowed\n"
            f"- Collision ON\n"
            f"- Dilarang Road Spawning\n"
            f"- Dilarang Menggunakan Plat Merah / Plat Polisi / Plat Militer\n"
            f"- Tidak Menggunakan Lajur Busway\n"
            f"--------------------\n"
            f"**SPEED LIMIT**\n"
            f"- Max Speed : 85\n"
            f"- Max Speed Gang : 30\n"
            f"--------------------\n"
            f"**FRP**\n"
            f"1x = Warn\n"
            f"2x = Kick\n"
            f"3x = Ban\n"
            f"--------------------\n"
            f"Code : {server_code}\n"
            f"Game Link :\n"
            f"https://www.roblox.com/games/6911148748/UPDATE-Car-Driving-Indonesia"
        )
        await channel.send(template)

# Modal Jendela Kedua (Pertanyaan 5 sampai 8)
class SessionPlannerPage2Modal(discord.ui.Modal, title="Session Technical Details"):
    staff_time = discord.ui.TextInput(label="5. Staff Join Time", placeholder="Format HH.MM (Example: 20.30)", max_length=5, required=True)
    server_code = discord.ui.TextInput(label="6. Server Code", placeholder="Please enter server code.", required=True)
    aorp_location = discord.ui.TextInput(label="7. AORP", placeholder="Please enter the AORP.", required=True)
    target_server = discord.ui.TextInput(label="8. Target Server Output Channel", placeholder="Enter 1, 2, or 3 only.", max_length=1, required=True)

    def __init__(self, session_id: str):
        super().__init__()
        self.session_id = session_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        selected_server = self.target_server.value.strip()
        if selected_server not in SERVER_CHANNELS:
            return await interaction.followup.send("Setup failed. Server destination selection must be either 1, 2, or 3.", ephemeral=True)

        time_str = self.staff_time.value.strip().replace(":", ".")
        try:
            hour, minute = map(int, time_str.split('.'))
        except ValueError:
            return await interaction.followup.send("Setup failed. Staff Join time specification must follow HH.MM format.", ephemeral=True)

        # Menggabungkan data dari Page 1 yang disimpan di memori global sementara
        page1_data = session_storage.get(self.session_id)
        if not page1_data:
            return await interaction.followup.send("Session data expired or lost. Please re-run !setsession.", ephemeral=True)

        announcement_text = (
            f"__**Rise Country**__\n"
            f" \n"
            f"<@819880959285395456>\n"
            f"{page1_data['day_date']}\n"
            f"-# <@&1354869839692562523> | @everyone\n"
            f" \n"
            f"__**Schedule**__\n"
            f" \n"
            f"{page1_data['schedules']}\n"
            f"- End session : Estimated at 11:00 pm or 12:00 pm (depending on the situation)\n"
            f" \n"
            f"Session time : {hour:02d}.{minute:02d} - Selesai (GMT +7)\n"
            f" \n"
            f"-# Note :\n"
            f"-# - Minimum requirement: 5 staff\n"
            f"-# - Please join at the scheduled time.\n"
            f"-# - The schedule may change at any time."
        )

        announcement_channel = bot.get_channel(ID_CHANNEL_ANNOUNCEMENT)
        if announcement_channel:
            await announcement_channel.send(announcement_text)
            chosen_channel_id = SERVER_CHANNELS[selected_server]

            scheduler.add_job(
                send_automated_strict_rp_template,
                'cron',
                hour=hour,
                minute=minute,
                args=[
                    chosen_channel_id,
                    page1_data["host_name"],
                    page1_data["map_author"],
                    self.aorp_location.value,
                    self.server_code.value
                ],
                id=f"strict_server_job_{self.session_id}"
            )
            # Bersihkan memori penampung
            session_storage.pop(self.session_id, None)
            
            # Ubah tampilan chat utama menandakan proses komplit
            await interaction.message.edit(content="✅ **Session Creation Complete!** Form data submitted and automated task scheduled successfully.", view=None)
            await interaction.followup.send("Form submission fully completed.", ephemeral=True)
        else:
            await interaction.followup.send("Configuration error. Destination channel could not be identified.", ephemeral=True)

# Modal Jendela Pertama (Pertanyaan 1 sampai 4)
class SessionPlannerPage1Modal(discord.ui.Modal, title="Create Roleplay Session"):
    host_name = discord.ui.TextInput(label="1. Host Identity", placeholder="Please enter the identity of the host.", required=True, max_length=100)
    map_author = discord.ui.TextInput(label="2. Map Author Identity", placeholder="Please enter the identity of the map author.", required=True, max_length=100)
    day_date = discord.ui.TextInput(label="3. Day, Date, and Time Session", placeholder="Example: Monday, 1 June 2026 at 21:00", required=True)
    schedules = discord.ui.TextInput(
        label="4. Schedules (Open Server, STS, Start Session)", 
        style=discord.TextStyle.long,
        placeholder="Open Server: 21.00\nSTS: 21.05\nRoleplay Start: 21.10", 
        required=True
    )

    def __init__(self, session_id: str):
        super().__init__()
        self.session_id = session_id

    async def on_submit(self, interaction: discord.Interaction):
        # Simpan sementara data dari halaman pertama ke global storage
        session_storage[self.session_id] = {
            "host_name": self.host_name.value,
            "map_author": self.map_author.value,
            "day_date": self.day_date.value,
            "schedules": self.schedules.value
        }
        
        # Tampilan Tombol Baru untuk Halaman Kedua (Menghindari Limitasi Modal Discord)
        class Page2TriggerView(discord.ui.View):
            def __init__(self, session_id: str):
                super().__init__(timeout=120)
                self.session_id = session_id
            @discord.ui.button(label="Click to Complete Technical Form (Page 2)", style=discord.ButtonStyle.primary)
            async def open_page2(self, inter: discord.Interaction, button: discord.ui.Button):
                await inter.response.send_modal(SessionPlannerPage2Modal(session_id=self.session_id))

        # Update pesan asli agar menginstruksikan pengguna membuka halaman 2
        await interaction.response.edit_message(
            content="**Part 1 Saved!** Please click the blue button below to complete the final part (Questions 5-8) of the session configuration.",
            view=Page2TriggerView(session_id=self.session_id)
        )

@bot.command(name="setsession")
async def start_session_planner(ctx):
    user_roles = [role.id for role in ctx.author.roles]
    has_permission = ctx.author.guild_permissions.administrator or any(role_id in user_roles for role_id in ALLOWED_ROLE_SESSION_IDS)
    
    if not has_permission: return

    instruction_text = (
        "Click the button below to complete and submit the roleplay session schedule form. "
        "Please ensure that all required information is entered accurately and completely to facilitate "
        "proper scheduling and coordination of the session."
    )
    
    session_id = str(ctx.message.id) # Token pengenal unik per sesi pengisian
    
    class TriggerView(discord.ui.View):
        def __init__(self, session_id: str):
            super().__init__(timeout=60)
            self.session_id = session_id
        @discord.ui.button(label="Click to Open Session Form", style=discord.ButtonStyle.secondary)
        async def open_form(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("Access denied.", ephemeral=True)
            await interaction.response.send_modal(SessionPlannerPage1Modal(session_id=self.session_id))

    await ctx.send(instruction_text, view=TriggerView(session_id=session_id))

# ====================================================================
# MANAGEMENT COMMANDS & ERROS
# ====================================================================
@bot.command(name="loasystem")
@commands.has_permissions(administrator=True)
async def toggle_loa_system(ctx, status: str = None):
    global loa_system_active
    if status is None:
        current_status = "ENABLED" if loa_system_active else "DISABLED"
        return await ctx.send(f"⚙️ **LOA System Status:** `{current_status}`")
    if status.lower() == "off":
        loa_system_active = False
        await ctx.send("The Leave of Absence (LOA) system has been temporarily disabled.")
    elif status.lower() == "on":
        loa_system_active = True
        await ctx.send("The Leave of Absence (LOA) system has been reactivated.")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_loa(ctx):
    embed = discord.Embed(title="Leave of Absence (LOA) Portal", description="Welcome to the Leave of Absence System.", color=discord.Color(0x0d50b8))
    await ctx.send(embed=embed, view=LOAButtonView())

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions): return
    raise error

@bot.event
async def on_ready():
    bot.add_view(LOAButtonView())
    if not check_expired_loa.is_running(): check_expired_loa.start()
    if not scheduler.running: scheduler.start()
    print(f"System Active! {bot.user} is operational.")

bot.run(os.getenv('DISCORD_TOKEN'))
