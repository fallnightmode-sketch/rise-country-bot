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
    @discord.ui.button(label="Accept Request", style=discord.ButtonStyle.success, custom_id="approve_loa_rail")
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

    @discord.ui.button(label="Reject Request", style=discord.ButtonStyle.danger, custom_id="reject_loa_rail")
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
    @discord.ui.button(label="Create LOA", style=discord.ButtonStyle.secondary, custom_id="button_create_loa_rail")
    async def create_loa_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not loa_system_active: return await interaction.response.send_message("The LOA system has been temporarily disabled.", ephemeral=True)
        await interaction.response.send_modal(LOAForm())


# ====================================================================
# SINGLE-PAGE UNIFIED ROLEPLAY PLANNER MODAL (STABLE)
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

class UnifiedSessionPlannerModal(discord.ui.Modal, title="Create Roleplay Session"):
    field_identities = discord.ui.TextInput(
        label="1 & 2. Host & Map Author Details",
        placeholder="Host Name: PRES | Doctor_BYP\nMap Author Name: ...",
        style=discord.TextStyle.long,
        required=True
    )
    field_day_date = discord.ui.TextInput(
        label="3. Day, Date, and Time Session",
        placeholder="Example: Tuesday, 26 May 2026 at 21.00",
        style=discord.TextStyle.short,
        required=True
    )
    field_schedules = discord.ui.TextInput(
        label="4. Schedules (Open Server, STS, Start)",
        placeholder="Open Server: 21.00\nSTS: 21.05\nRoleplay Start: 21.10",
        style=discord.TextStyle.long,
        required=True
    )
    field_tech_details = discord.ui.TextInput(
        label="5 & 6. Staff Join Time & Server Code",
        placeholder="Staff Join Time (Format HH.MM): 20.30\nServer Code: rcrp-test-code",
        style=discord.TextStyle.long,
        required=True
    )
    field_venue_channel = discord.ui.TextInput(
        label="7 & 8. AORP & Target Server Channel",
        placeholder="AORP Venue: Gedung DPR-RI\nTarget Channel Server (Ketik angka 1, 2, atau 3): 1",
        style=discord.TextStyle.long,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Parse Host & Map Author
        id_lines = [line.strip() for line in self.field_identities.value.split('\n') if line.strip()]
        host_name = "Staff RCRP"
        map_author = "Staff RCRP"
        for line in id_lines:
            if "host" in line.lower():
                host_name = line.split(':', 1)[-1].strip()
            elif "map" in line.lower():
                map_author = line.split(':', 1)[-1].strip()

        # Parse Tech Details
        tech_lines = [line.strip() for line in self.field_tech_details.value.split('\n') if line.strip()]
        staff_time_str = "20.30"
        server_code = "PRIVATE-SERVER"
        for line in tech_lines:
            if "time" in line.lower() or "join" in line.lower():
                staff_time_str = line.split(':', 1)[-1].strip().replace(":", ".")
            elif "code" in line.lower() or "server" in line.lower():
                server_code = line.split(':', 1)[-1].strip()

        # Parse Venue & Target Channel
        venue_lines = [line.strip() for line in self.field_venue_channel.value.split('\n') if line.strip()]
        aorp_location = "LOC"
        selected_server = "1"
        for line in venue_lines:
            if "aorp" in line.lower() or "venue" in line.lower():
                aorp_location = line.split(':', 1)[-1].strip()
            elif "channel" in line.lower() or "target" in line.lower() or "server" in line.lower():
                selected_server = "".join(filter(str.isdigit, line.split(':', 1)[-1].strip()))

        if selected_server not in SERVER_CHANNELS:
            return await interaction.followup.send("Setup failed. Server channel must be 1, 2, or 3.", ephemeral=True)

        try:
            time_clean = "".join([c for c in staff_time_str if c.isdigit() or c == '.'])
            hour, minute = map(int, time_clean.split('.'))
        except Exception:
            return await interaction.followup.send("Setup failed. Staff Join Time must follow HH.MM format.", ephemeral=True)

        announcement_text = (
            f"__**Rise Country**__\n"
            f" \n"
            f"<@819880959285395456>\n"
            f"{self.field_day_date.value}\n"
            f"-# <@&1354869839692562523> | @everyone\n"
            f" \n"
            f"__**Schedule**__\n"
            f" \n"
            f"{self.field_schedules.value}\n"
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
                args=[chosen_channel_id, host_name, map_author, aorp_location, server_code],
                id=f"strict_job_{interaction.id}"
            )
            try:
                await interaction.message.delete()
            except Exception:
                pass
            await interaction.followup.send(f"Success! Schedule created and template automated for Server {selected_server}.", ephemeral=True)
        else:
            await interaction.followup.send("Error. Main announcement channel not found.", ephemeral=True)

@bot.command(name="setsession")
async def start_session_planner(ctx):
    user_roles = [role.id for role in ctx.author.roles]
    has_permission = ctx.author.guild_permissions.administrator or any(role_id in user_roles for role_id in ALLOWED_ROLE_SESSION_IDS)
    
    if not has_permission: return

    instruction_text = (
        "Click the button below to open the complete session schedule form. "
        "Please read the guide details inside each field carefully."
    )
    
    class TriggerView(discord.ui.View):
        def __init__(self): super().__init__(timeout=60)
        @discord.ui.button(label="Click to Open Session Form", style=discord.ButtonStyle.secondary, custom_id="btn_open_session_railway")
        async def open_form(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != ctx.author.id:
                return await interaction.response.send_message("Access denied.", ephemeral=True)
            await interaction.response.send_modal(UnifiedSessionPlannerModal())

    await ctx.send(instruction_text, view=TriggerView())

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
