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
    @discord.ui.button(label="Accept Request", style=discord.ButtonStyle.success, custom_id="approve_loa_v6")
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

    @discord.ui.button(label="Reject Request", style=discord.ButtonStyle.danger, custom_id="reject_loa_v6")
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
    @discord.ui.button(label="Create LOA", style=discord.ButtonStyle.secondary, custom_id="button_create_loa_v6")
    async def create_loa_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not loa_system_active: return await interaction.response.send_message("The LOA system has been temporarily disabled.", ephemeral=True)
        await interaction.response.send_modal(LOAForm())


# ====================================================================
# TWO-PAGE PROFESSIONAL ROLEPLAY SESSION PLANNER
# ====================================================================

async def send_automated_strict_rp_template(target_channel_id, host_name, map_author, aorp_loc, server_code):
    channel = bot.get_channel(target_channel_id)
    if channel:
        # PERBAIKAN UTAMA: Struktur string dipecah secara linear agar aman dari pemotongan API Discord
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

class SessionPlannerPage2Modal(discord.ui.Modal, title="Page 2: Technical & Venue"):
    f_staff_join = discord.ui.TextInput(
        label="5. Staff Join Time",
        placeholder="Please enter the exact time for staff assembly (e.g., 20.30)",
        style=discord.TextStyle.short,
        required=True
    )
    f_code = discord.ui.TextInput(
        label="6. Server Code",
        placeholder="Provide the designated Private Server link/code identifier",
        style=discord.TextStyle.short,
        required=True
    )
    f_aorp = discord.ui.TextInput(
        label="7. AORP Region / City",
        placeholder="Enter the targeted city region (e.g., Bekasi, Bandung, Jakarta)",
        style=discord.TextStyle.short,
        required=True
    )
    f_channel = discord.ui.TextInput(
        label="8. Channel Number",
        placeholder="Select target server channel (Type only: 1, 2, or 3)",
        style=discord.TextStyle.short,
        required=True
    )

    def __init__(self, cached_data):
        super().__init__()
        self.cached_data = cached_data

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        selected_server = self.f_channel.value.strip()
        if selected_server not in SERVER_CHANNELS:
            return await interaction.followup.send("❌ Submission aborted. Target Channel must be 1, 2, or 3.", ephemeral=True)

        staff_time_raw = self.f_staff_join.value.strip().replace(":", ".")
        try:
            time_clean = "".join([c for c in staff_time_raw if c.isdigit() or c == '.'])
            hour, minute = map(int, time_clean.split('.'))
        except Exception:
            return await interaction.followup.send("❌ Submission aborted. Staff Join Time must follow the HH.MM format.", ephemeral=True)

        open_server_time = staff_time_raw  
        match = re.search(r'(?:open\s+server|open)\s*:\s*([\d[:\.]+)', self.cached_data['schedules'].lower())
        if match:
            open_server_time = match.group(1).strip().replace(":", ".")

        announcement_text = (
            f"__**Rise Country**__\n"
            f" \n"
            f"{self.cached_data['host']}\n"
            f"{self.cached_data['day_date']}\n"
            f"-# <@&1354869839692562523> | @everyone\n"
            f" \n"
            f"__**Schedule**__\n"
            f" \n"
            f"{self.cached_data['schedules']}\n"
            f"Staff Join Time: {staff_time_raw}\n"
            f"End Session: {self.cached_data['end_time']}\n"
            f" \n"
            f"Session time : {open_server_time} - {self.cached_data['end_time']} (GMT +7)\n"
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
                args=[chosen_channel_id, self.cached_data['host'], self.cached_data['map_author'], self.f_aorp.value.strip(), self.f_code.value.strip()],
                id=f"strict_job_v6_{interaction.id}"
            )
            
            try:
                await interaction.message.delete()
            except Exception:
                pass
            
            success_embed = discord.Embed(
                title="✨ Session Created Successfully!",
                description=(
                    f"• Announcement posted in main channel.\n"
                    f"• Strict RP template scheduled for automated delivery to **Server {selected_server}** at **{staff_time_raw}**."
                ),
                color=discord.Color(0x0d50b8)
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)
        else:
            await interaction.followup.send("❌ Configuration Error: Main announcement channel could not be resolved.", ephemeral=True)

class SessionPlannerPage1Modal(discord.ui.Modal, title="Page 1: Identity & Schedule"):
    f_host = discord.ui.TextInput(
        label="1. Host Server",
        placeholder="State the official designated host identity name",
        style=discord.TextStyle.short,
        required=True
    )
    f_map = discord.ui.TextInput(
        label="2. Map Author",
        placeholder="Provide credit declaration for the map developer",
        style=discord.TextStyle.short,
        required=True
    )
    f_day_date = discord.ui.TextInput(
        label="3. Day, Date, and Time Session",
        placeholder="Format standard example: Tuesday, 26 May 2026 at 21.00",
        style=discord.TextStyle.short,
        required=True
    )
    f_schedules = discord.ui.TextInput(
        label="4. Schedule Milestones",
        placeholder="Open Server: 21.00\nSTS: 21.05\nRoleplay Start: 21.10",
        style=discord.TextStyle.long,
        required=True
    )
    f_end = discord.ui.TextInput(
        label="4b. End Session Time",
        placeholder="Specify session closure time target (e.g., 23.30)",
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        cached_data = {
            "host": self.f_host.value.strip(),
            "map_author": self.f_map.value.strip(),
            "day_date": self.f_day_date.value.strip(),
            "schedules": self.f_schedules.value.strip(),
            "end_time": self.f_end.value.strip()
        }
        
        transition_embed = discord.Embed(
            title="📥 Page 1 Complete!",
            description="Click the button below to proceed and finalize the technical configurations on Page 2.",
            color=discord.Color(0x0d50b8)
        )
        
        class TransitionView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
            @discord.ui.button(label="Proceed to Page 2", style=discord.ButtonStyle.secondary, custom_id="btn_goto_p2_v6")
            async def go_page2(self, inner_interaction: discord.Interaction, button: discord.ui.Button):
                await inner_interaction.response.send_modal(SessionPlannerPage2Modal(cached_data=cached_data))

        await interaction.response.send_message(embed=transition_embed, view=TransitionView(), ephemeral=True)

@bot.command(name="setsession")
async def start_session_planner(ctx):
    user_roles = [role.id for role in ctx.author.roles]
    has_permission = ctx.author.guild_permissions.administrator or any(role_id in user_roles for role_id in ALLOWED_ROLE_SESSION_IDS)
    
    if not has_permission: 
        return

    trigger_embed = discord.Embed(
        title="📑 Session Creation Portal",
        description="Click the configuration button below to access **Page 1** of the professional session formulation wizard.",
        color=discord.Color(0x0d50b8)
    )
    
    class WizardTriggerView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
        @discord.ui.button(label="Create Session Plan", style=discord.ButtonStyle.secondary, custom_id="btn_trigger_p1_v6")
        async def open_p1(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("Authorization denied.", ephemeral=True)
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
    print(f"System Active! {bot.user} is operational.")

token = os.getenv('DISCORD_TOKEN')
if token:
    bot.run(token)
else:
    print("ERROR: DISCORD_TOKEN variable is completely missing from Railway dashboard configuration.")
