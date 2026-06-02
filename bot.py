import sys
import subprocess
import re

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

# Channel Utama untuk Pengumuman Sesi & Format Staff Join
ID_CHANNEL_ANNOUNCEMENT = 1400173631421546620 

# Target 3 Channel untuk Template Strict RP (Open Server)
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
# AUTOMATIC CHECKER TASK FOR LOA
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
    @discord.ui.button(label="Accept Request", style=discord.ButtonStyle.success, custom_id="approve_loa_v9")
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

    @discord.ui.button(label="Reject Request", style=discord.ButtonStyle.danger, custom_id="reject_loa_v9")
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
            embed = discord.Embed(title="PENDING LOA REQUEST", description=f"Submission from {member.mention}", color=discord.Color(0x0d50b8))
            await log_channel.send(embed=embed, view=AdminApprovalView(member_id=member.id, data_form={"username": self.q1.value, "end_date": self.q3.value}))
            await interaction.followup.send("Your LOA request has been securely submitted.", ephemeral=True)

class LOAButtonView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Create LOA", style=discord.ButtonStyle.secondary, custom_id="button_create_loa_v9")
    async def create_loa_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not loa_system_active: return await interaction.response.send_message("The LOA system has been temporarily disabled.", ephemeral=True)
        await interaction.response.send_modal(LOAForm())


# ====================================================================
# AUTOMATED SCHEDULER EXECUTIONS
# ====================================================================

# Pemicu Otomatis 1: Mengirim info singkat [Code] & [AORP] saat jam STAFF JOIN
async def send_staff_join_reminder(aorp_loc, server_code):
    channel = bot.get_channel(ID_CHANNEL_ANNOUNCEMENT)
    if channel:
        reminder_text = (
            f"📢 **Staff Join Reminder!**\n"
            f"**AORP:** {aorp_loc}\n"
            f"**Server Code:** || {server_code} ||"
        )
        await channel.send(content=reminder_text)

# Pemicu Otomatis 2: Mengirim Template Panjang STRICT RP saat jam OPEN SERVER
async def send_open_server_strict_template(target_channel_id, host_name, map_author, aorp_loc, server_code):
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
        await channel.send(content=template)


# ====================================================================
# TWO-PAGE MODAL SESSION PLANNER SYSTEM
# ====================================================================

class SessionPlannerPage2Modal(discord.ui.Modal, title="Page 2: Milestones & Venue"):
    f_sts = discord.ui.TextInput(
        label="3) STS Time", placeholder="Example: 21.05", style=discord.TextStyle.short, required=True
    )
    f_rp_start = discord.ui.TextInput(
        label="4) Roleplay Start Time", placeholder="Example: 21.10", style=discord.TextStyle.short, required=True
    )
    f_end = discord.ui.TextInput(
        label="5) End Session Time", placeholder="Example: 23.30", style=discord.TextStyle.short, required=True
    )
    f_code = discord.ui.TextInput(
        label="Server Private Code", placeholder="Enter server link or code text", style=discord.TextStyle.short, required=True
    )
    f_channel = discord.ui.TextInput(
        label="Target Strict RP Channel Number", placeholder="Type only: 1, 2, or 3", style=discord.TextStyle.short, required=True
    )

    def __init__(self, cached_page1, aorp_loc):
        super().__init__()
        self.cached_page1 = cached_page1
        self.aorp_loc = aorp_loc

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        selected_server = self.f_channel.value.strip()
        if selected_server not in SERVER_CHANNELS:
            return await interaction.followup.send("❌ Submission aborted. Channel option must be 1, 2, or 3.", ephemeral=True)

        # --- PARSING JAM STAFF JOIN ---
        staff_raw = self.cached_page1["staff_join"].replace(":", ".")
        try:
            staff_clean = "".join([c for c in staff_raw if c.isdigit() or c == '.'])
            s_hour, s_minute = map(int, staff_clean.split('.'))
        except Exception:
            return await interaction.followup.send("❌ Formatting error in Staff Join Time (Use HH.MM format).", ephemeral=True)

        # --- PARSING JAM OPEN SERVER ---
        open_raw = self.cached_page1["open_server"].replace(":", ".")
        try:
            open_clean = "".join([c for c in open_raw if c.isdigit() or c == '.'])
            o_hour, o_minute = map(int, open_clean.split('.'))
        except Exception:
            return await interaction.followup.send("❌ Formatting error in Open Server Time (Use HH.MM format).", ephemeral=True)

        # --- BUILD TEXT JADWAL UTAMA ---
        # Mengotomatisasi poin 6) Session Time: [Jam Open Server] - [Jam End Session]
        session_time_computed = f"{self.cached_page1['open_server']} - {self.f_end.value.strip()}"

        announcement_text = (
            f"__**Rise Country**__\n"
            f" \n"
            f"Host : {self.cached_page1['host']}\n"
            f"Day, Date : {self.cached_page1['day_date']}\n"
            f"-# <@&1354869839692562523> | @everyone\n"
            f" \n"
            f"__**Schedule**__\n"
            f" \n"
            f"Open Server : {self.cached_page1['open_server']}\n"
            f"STS : {self.f_sts.value.strip()}\n"
            f"Roleplay Start : {self.f_rp_start.value.strip()}\n"
            f"Staff Join Time : {self.cached_page1['staff_join']}\n"
            f"End Session : {self.f_end.value.strip()}\n"
            f" \n"
            f"Session time : {session_time_computed} (GMT +7)\n"
            f" \n"
            f"-# Note :\n"
            f"-# - Minimum requirement: 5 staff\n"
            f"-# - Please join at the scheduled time.\n"
            f"-# - The schedule may change at any time."
        )

        announcement_channel = bot.get_channel(ID_CHANNEL_ANNOUNCEMENT)
        if announcement_channel:
            # 1. Kirim Pengumuman Utama Secara Instan
            await announcement_channel.send(announcement_text)

            # 2. Jadwalkan Pengiriman Pengingat [Code] saat jam STAFF JOIN
            scheduler.add_job(
                send_staff_join_reminder,
                'cron',
                hour=s_hour,
                minute=s_minute,
                args=[self.aorp_loc, self.f_code.value.strip()],
                id=f"staff_join_job_{interaction.id}"
            )

            # 3. Jadwalkan Pengiriman Template Panjang STRICT RP saat jam OPEN SERVER
            chosen_channel_id = SERVER_CHANNELS[selected_server]
            scheduler.add_job(
                send_open_server_strict_template,
                'cron',
                hour=o_hour,
                minute=o_minute,
                args=[chosen_channel_id, self.cached_page1['host'], self.cached_page1['map_author'], self.aorp_loc, self.f_code.value.strip()],
                id=f"open_server_job_{interaction.id}"
            )
            
            try: await interaction.message.delete()
            except Exception: pass
            
            success_embed = discord.Embed(
                title="✨ Session Automated Perfectly!",
                description=(
                    f"• **Main Announcement** posted instantly.\n"
                    f"• **Staff Join Reminder** scheduled at **{self.cached_page1['staff_join']}** (Main Channel).\n"
                    f"• **Strict RP Template** scheduled at **{self.cached_page1['open_server']}** (Server Channel {selected_server})."
                ),
                color=discord.Color(0x0d50b8)
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)
        else:
            await interaction.followup.send("❌ Channel Configuration Error.", ephemeral=True)


class SessionPlannerPage1Modal(discord.ui.Modal, title="Page 1: Basic & Timing Info"):
    f_host = discord.ui.TextInput(
        label="Host Server Name", placeholder="e.g. @ Name", style=discord.TextStyle.short, required=True
    )
    f_map = discord.ui.TextInput(
        label="Map Author Credit", placeholder="e.g. @ Name", style=discord.TextStyle.short, required=True
    )
    f_day_date = discord.ui.TextInput(
        label="Day & Date Session", placeholder="e.g. Tuesday, 26 May 2026", style=discord.TextStyle.short, required=True
    )
    f_staff = discord.ui.TextInput(
        label="1) Staff Join Time", placeholder="e.g. 21.10", style=discord.TextStyle.short, required=True
    )
    f_open = discord.ui.TextInput(
        label="2) Open Server Time", placeholder="e.g. 21.15", style=discord.TextStyle.short, required=True
    )
    f_aorp = discord.ui.TextInput(
        label="AORP Location / City", placeholder="e.g. Bandung", style=discord.TextStyle.short, required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        cached_page1 = {
            "host": self.f_host.value.strip(),
            "map_author": self.f_map.value.strip(),
            "day_date": self.f_day_date.value.strip(),
            "staff_join": self.f_staff.value.strip(),
            "open_server": self.f_open.value.strip()
        }
        aorp_loc = self.f_aorp.value.strip()
        
        transition_embed = discord.Embed(
            title="📥 Page 1 Captured!",
            description="Proceed to Page 2 to input remaining timestamps (STS, RP Start, End) and target venue details.",
            color=discord.Color(0x0d50b8)
        )
        
        class TransitionView(discord.ui.View):
            def __init__(self): super().__init__(timeout=60)
            @discord.ui.button(label="Proceed to Page 2", style=discord.ButtonStyle.secondary, custom_id="btn_to_p2_final")
            async def go_page2(self, inner_interaction: discord.Interaction, button: discord.ui.Button):
                await inner_interaction.response.send_modal(SessionPlannerPage2Modal(cached_page1=cached_page1, aorp_loc=aorp_loc))

        await interaction.response.send_message(embed=transition_embed, view=TransitionView(), ephemeral=True)


@bot.command(name="setsession")
async def start_session_planner(ctx):
    user_roles = [role.id for role in ctx.author.roles]
    has_permission = ctx.author.guild_permissions.administrator or any(role_id in user_roles for role_id in ALLOWED_ROLE_SESSION_IDS)
    
    if not has_permission: return

    trigger_embed = discord.Embed(
        title="📑 Session Scheduling Portal",
        description="Click the layout planner button down below to configure all structured milestone times.",
        color=discord.Color(0x0d50b8)
    )
    
    class WizardTriggerView(discord.ui.View):
        def __init__(self): super().__init__(timeout=60)
        @discord.ui.button(label="Open Planner Form", style=discord.ButtonStyle.secondary, custom_id="btn_run_p1_final")
        async def open_p1(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("Unauthorized user interaction.", ephemeral=True)
            await interaction.response.send_modal(SessionPlannerPage1Modal())

    await ctx.send(embed=trigger_embed, view=WizardTriggerView())

# ====================================================================
# MANAGEMENT COMMANDS & ERRORS
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
    print(f"System Active! {bot.user} is fully calibrated.")

token = os.getenv('DISCORD_TOKEN')
if token:
    bot.run(token)
else:
    print("ERROR: DISCORD_TOKEN is missing.")
