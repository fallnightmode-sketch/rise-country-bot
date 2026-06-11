import sys
import os
import json
import time
import re
from datetime import datetime

# ====================================================================
# IMPORT UTAMA DISCORD & APSCHEDULER
# ====================================================================
import discord
from discord.ext import commands, tasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  

bot = commands.Bot(command_prefix="!", intents=intents)

JAKARTA_TZ = pytz.timezone("Asia/Jakarta")
scheduler = AsyncIOScheduler(timezone=JAKARTA_TZ)

# ====================================================================
# KONSTANTA KONFIGURASI (Rise Country Official Only)
# ====================================================================
GUILD_ID = 1351182942625337378            
ID_CHANNEL_LOG_LOA = 1510642659776266442  
ID_ROLE_LOA = 1469270847905730590         
DATA_FILE = "loa_data.json"

ID_ROLE_PEMERINTAH = 1354869839692562523   
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
# DATABASE LOA LOKAL
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

def convert_to_user_mention(guild, input_text):
    if not guild or not input_text:
        return input_text
    input_text = input_text.strip()
    match_id = re.search(r'\d+', input_text)
    if match_id and ("<@" in input_text or len(input_text) >= 17):
        return f"<@{match_id.group()}>"
    clean_name = input_text.replace("@", "").split("|")[-1].strip().lower()
    for member in guild.members:
        if member.display_name.lower() == clean_name: return member.mention
        if member.name.lower() == clean_name: return member.mention
        if clean_name in member.display_name.lower() or clean_name in member.name.lower(): return member.mention
    return input_text

@tasks.loop(hours=1.0)
async def check_expired_loa():
    guild = bot.get_guild(GUILD_ID)
    if not guild: return
    role_loa = guild.get_role(ID_ROLE_LOA)
    if not role_loa: return
    loa_data = load_loa_data()
    now = datetime.now(JAKARTA_TZ)
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
                            description=f"Hello {member.mention},\n\nYour Leave of Absence (LOA) period has concluded.",
                            color=discord.Color(0x0d50b8)
                        )
                        await member.send(embed=embed_dm)
                    except Exception: pass
                del loa_data[member_id_str]
                updated = True
        except ValueError: continue
    if updated: save_loa_data(loa_data)

# ====================================================================
# LOGIKA MODAL LOA (SECURED)
# ====================================================================
class RejectReasonModal(discord.ui.Modal, title="LOA Rejection Reason"):
    reason = discord.ui.TextInput(label="Reason for Rejection", placeholder="e.g. Input administrative rejection grounds here...", style=discord.TextStyle.long, required=True, max_length=300)

    def __init__(self, member_id: int, interaction_admin: discord.Interaction, view_approval):
        super().__init__()
        self.member_id = member_id
        self.interaction_admin = interaction_admin
        self.view_approval = view_approval

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID: return  
        await interaction.response.defer()

        guild = interaction.guild
        member = guild.get_member(self.member_id)

        embed = self.interaction_admin.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "LOA REQUEST - REJECTED"
        embed.add_field(name="Reason for Rejection", value=self.reason.value, inline=False)

        await self.interaction_admin.message.edit(embed=embed, view=self.view_approval)

        if member:
            try:
                embed_dm = discord.Embed(
                    title="Your LOA Request Has Been Rejected",
                    description=(
                        f"Hello {member.mention},\n\n"
                        f"We regret to inform you that your Leave of Absence (LOA) request has been "
                        f"reviewed and rejected by the administration.\n\n"
                        f"**Reason:** {self.reason.value}\n\n"
                        f"Please contact the President or Vice President for further clarification."
                    ),
                    color=discord.Color.red()
                )
                await member.send(embed=embed_dm)
            except Exception: pass

class AdminApprovalView(discord.ui.View):
    def __init__(self, member_id: int, data_form: dict):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.data_form = data_form
        
    @discord.ui.button(label="Accept Request", style=discord.ButtonStyle.success, custom_id="approve_loa_v14")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != GUILD_ID: return  
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
            loa_data[str(self.member_id)] = {
                "username": self.data_form["username"], 
                "position": self.data_form["position"],
                "start_date": self.data_form["start_date"],
                "end_date": self.data_form["end_date"]
            }
            save_loa_data(loa_data)
            
            try:
                embed_dm = discord.Embed(
                    title="Your LOA Request Has Been Approved",
                    description=(
                        f"Hello {member.mention},\n\n"
                        f"Your Leave of Absence (LOA) request has been successfully approved.\n\n"
                        f"**Duration:**\n"
                        f"{self.data_form['start_date']} - {self.data_form['end_date']}\n\n"
                        f"The Leave of Absence role has been assigned."
                    ),
                    color=discord.Color.green()
                )
                await member.send(embed=embed_dm)
            except Exception: pass

    @discord.ui.button(label="Reject Request", style=discord.ButtonStyle.danger, custom_id="reject_loa_v14")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != GUILD_ID: return
        for child in self.children: child.disabled = True
        await interaction.response.send_modal(RejectReasonModal(member_id=self.member_id, interaction_admin=interaction, view_approval=self))

class LOAForm(discord.ui.Modal, title="Leave of Absence Application"):
    q1 = discord.ui.TextInput(label="1. Roblox Username", placeholder="Please enter your Roblox username.", required=True, max_length=50)
    q2 = discord.ui.TextInput(label="2. Position / Department", placeholder="Please enter your position or department.", required=True, max_length=70)
    q3 = discord.ui.TextInput(label="3. LOA Start Date (DD/MM/YYYY)", placeholder="e.g., 10/06/2026", required=True, max_length=15)
    q4 = discord.ui.TextInput(label="4. LOA End Date (DD/MM/YYYY)", placeholder="e.g., 17/06/2026", required=True, max_length=15)
    q5 = discord.ui.TextInput(label="5. Reason & Notes", placeholder="Please provide the reason regarding your leave request.", style=discord.TextStyle.long, required=True, max_length=400)
    
    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID: return
        member = interaction.user
        await interaction.response.defer(ephemeral=True)
        
        try: 
            datetime.strptime(self.q3.value.strip(), "%d/%m/%Y")
            datetime.strptime(self.q4.value.strip(), "%d/%m/%Y")
        except ValueError:
            return await interaction.followup.send("Submission failed! Invalid date format. Use DD/MM/YYYY.", ephemeral=True)
            
        log_channel = bot.get_channel(ID_CHANNEL_LOG_LOA)
        if log_channel:
            embed = discord.Embed(title="PENDING LOA REQUEST", description=f"Submission from {member.mention}", color=discord.Color(0x0d50b8))
            embed.add_field(name="1. Roblox Username", value=self.q1.value, inline=True)
            embed.add_field(name="2. Position / Department", value=self.q2.value, inline=True)
            embed.add_field(name="3. LOA Start Date", value=self.q3.value, inline=True)
            embed.add_field(name="4. LOA End Date", value=self.q4.value, inline=True)
            embed.add_field(name="5. Reason & Notes", value=self.q5.value, inline=False)
            
            data_payload = {
                "username": self.q1.value, 
                "position": self.q2.value,
                "start_date": self.q3.value,
                "end_date": self.q4.value
            }
            await log_channel.send(embed=embed, view=AdminApprovalView(member_id=member.id, data_form=data_payload))
            await interaction.followup.send("Your LOA request has been securely submitted.", ephemeral=True)

class LOAButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Create LOA", style=discord.ButtonStyle.success, custom_id="btn_create_loa_portal")
    async def create_loa_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not loa_system_active:
            return await interaction.response.send_message("The LOA system is currently disabled.", ephemeral=True)
        await interaction.response.send_modal(LOAForm())

# ====================================================================
# Leave Of Absence List
# ====================================================================
@bot.command(name="list_loa")
async def list_active_loa(ctx):
    if ctx.guild is None or ctx.guild.id != GUILD_ID: return
    
    user_roles = [role.id for role in ctx.author.roles]
    has_permission = ctx.author.guild_permissions.administrator or any(role_id in user_roles for role_id in ALLOWED_ROLE_SESSION_IDS)
    if not has_permission: return

    loa_data = load_loa_data()
    
    if not loa_data:
        embed_empty = discord.Embed(
            title="Active LOA Members",
            description="❌ Tidak ada staff yang sedang dalam masa Leave of Absence (LOA) saat ini.",
            color=discord.Color.red()
        )
        return await ctx.send(embed=embed_empty)

    embed_list = discord.Embed(
        title="📋 Active LOA Database",
        description="Daftar staff yang sedang mengambil masa cuti aktif saat ini:",
        color=discord.Color(0x0d50b8)
    )

    for member_id_str, details in loa_data.items():
        pos = details.get("position", "-")
        s_date = details.get("start_date", "-")
        e_date = details.get("end_date", "-")
        
        format_text = (
            f"**Roblox Username:** {details['username']}\n"
            f"**Position/Department:** {pos}\n"
            f"**Start Date - End Date:** {s_date} - {e_date}"
        )
        
        embed_list.add_field(
            name="📋 Leave of Absence",
            value=format_text,
            inline=False
        )

    await ctx.send(embed=embed_list)

# ====================================================================
# FUNGSI CRON EKSEKUSI OTOMATIS
# ====================================================================
async def send_staff_join_reminder(aorp_loc, server_code):
    channel = bot.get_channel(ID_CHANNEL_ANNOUNCEMENT)
    if channel:
        reminder_text = (
            f"<@&{ID_ROLE_PEMERINTAH}>\n"
            f"AORP: {aorp_loc}\n"
            f"Server Code: {server_code}\n\n"
            f"-# Notes:\n"
            f"-# - Anda memiliki waktu 10 menit sejak kode ini dibagikan untuk bergabung ke dalam server.\n"
            f"-# - Harap menggunakan seragam kerja Rise Country selama bertugas.\n"
        )
        await channel.send(content=reminder_text)

async def send_open_server_strict_template(target_channel_id, host_tag, map_author, aorp_loc, server_code):
    channel = bot.get_channel(target_channel_id)
    if channel:
        template = (
            f"# **RiseCountry 🔴 STRICT RP**\n"
            f"**AORP : {aorp_loc}**\n"
            f"Code : {server_code}\n"
        )
        await channel.send(content=template)

# ====================================================================
# TWO-STAGE MODAL
# ====================================================================
class SessionPlannerPage2Modal(discord.ui.Modal, title="Page 2: Milestone Configurations"):
    f_staff = discord.ui.TextInput(label="1) Staff Join Time (HH.MM)", placeholder="21.00", required=True)
    f_open = discord.ui.TextInput(label="2) Open Server Time (HH.MM)", placeholder="21.10", required=True)
    f_sts = discord.ui.TextInput(label="3) STS Time (HH.MM)", placeholder="21.15", required=True)
    f_rp_start = discord.ui.TextInput(label="4) Roleplay Start Time (HH.MM)", placeholder="21.20", required=True)
    f_end = discord.ui.TextInput(label="5) End Session Time (HH.MM)", placeholder="23.00", required=True)

    def __init__(self, data_p1: dict):
        super().__init__()
        self.data_p1 = data_p1

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID: return  
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        host_tag = convert_to_user_mention(guild, self.data_p1['host'])
        
        try:
            staff_clean = re.sub(r'[^0-9.]', '', self.f_staff.value.strip().replace(":", "."))
            s_hour, s_min = map(int, staff_clean.split('.'))
            open_clean = re.sub(r'[^0-9.]', '', self.f_open.value.strip().replace(":", "."))
            o_hour, o_min = map(int, open_clean.split('.'))
        except Exception:
            return await interaction.followup.send("Format waktu salah! Gunakan titik (contoh: 21.00).", ephemeral=True)

        session_time_computed = f"{self.f_open.value.strip()} - {self.f_end.value.strip()}"

        announcement_text = f"__**Rise Country Session**__\nHost: {host_tag}\nTime: {session_time_computed}"

        announcement_channel = bot.get_channel(ID_CHANNEL_ANNOUNCEMENT)
        if announcement_channel:
            await announcement_channel.send(announcement_text)
            
            scheduler.add_job(send_staff_join_reminder, 'cron', hour=s_hour, minute=s_min, args=[self.data_p1['aorp'], self.data_p1['code']], id=f"sj_{int(time.time())}")
            chosen_channel_id = SERVER_CHANNELS[self.data_p1['channel']]
            scheduler.add_job(send_open_server_strict_template, 'cron', hour=o_hour, minute=o_min, args=[chosen_channel_id, host_tag, convert_to_user_mention(guild, self.data_p1['map_author']), self.data_p1['aorp'], self.data_p1['code']], id=f"os_{int(time.time())}")

            await interaction.followup.send("Scheduler Activated Successfully!", ephemeral=True)

class SessionPlannerPage1Modal(discord.ui.Modal, title="Page 1: Identity & Parameters"):
    f_host = discord.ui.TextInput(label="Host Name", required=True)
    f_map = discord.ui.TextInput(label="Map Author Credit", required=True)
    f_day_date = discord.ui.TextInput(label="Day & Date", required=True)
    f_aorp = discord.ui.TextInput(label="AORP Location / City", required=True)
    f_code = discord.ui.TextInput(label="Server Private Code / Link", required=True)

    def __init__(self, selected_channel: str):
        super().__init__()
        self.selected_channel = selected_channel

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID: return
        data_p1 = {
            "host": self.f_host.value.strip(), "map_author": self.f_map.value.strip(),
            "day_date": self.f_day_date.value.strip(), "aorp": self.f_aorp.value.strip(),
            "code": self.f_code.value.strip(), "channel": self.selected_channel
        }

        class NextStageView(discord.ui.View):
            def __init__(self): super().__init__(timeout=120)
            @discord.ui.button(label="Proceed to Page 2", style=discord.ButtonStyle.primary)
            async def open_p2(self, inner_interaction: discord.Interaction, button: discord.ui.Button):
                await inner_interaction.response.send_modal(SessionPlannerPage2Modal(data_p1=data_p1))

        await interaction.response.send_message("Parameters recorded.", view=NextStageView(), ephemeral=True)

class ChannelSelectComponent(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label="Channel 1", value="1"), discord.SelectOption(label="Channel 2", value="2"), discord.SelectOption(label="Channel 3", value="3")]
        super().__init__(placeholder="Select Target Channel...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID: return
        await interaction.response.send_modal(SessionPlannerPage1Modal(selected_channel=self.values[0]))

class WizardTriggerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ChannelSelectComponent())

# ====================================================================
# UTILITY COMMANDS
# ====================================================================
@bot.command(name="setsession")
async def start_session_planner(ctx):
    if ctx.guild is None or ctx.guild.id != GUILD_ID: return
    user_roles = [role.id for role in ctx.author.roles]
    if ctx.author.guild_permissions.administrator or any(role_id in user_roles for role_id in ALLOWED_ROLE_SESSION_IDS):
        await ctx.send("Session Scheduling Portal", view=WizardTriggerView())

@bot.command(name="end_loa")
@commands.has_permissions(administrator=True)
async def remove_loa_manual(ctx, member: discord.Member = None):
    if ctx.guild is None or ctx.guild.id != GUILD_ID or not member: return
    role_loa = ctx.guild.get_role(ID_ROLE_LOA)
    if role_loa and role_loa in member.roles:
        await member.remove_roles(role_loa)
    loa_data = load_loa_data()
    if str(member.id) in loa_data:
        del loa_data[str(member.id)]
        save_loa_data(loa_data)
    await ctx.send(f"LOA terminated for {member.display_name}.")

@bot.command(name="loasystem")
@commands.has_permissions(administrator=True)
async def toggle_loa_system(ctx, status: str = None):
    global loa_system_active
    if not status: return await ctx.send(f"LOA Status: {loa_system_active}")
    loa_system_active = status.lower() == "on"
    await ctx.send(f"LOA System updated to {loa_system_active}")

@bot.command(name="setup_loa")
@commands.has_permissions(administrator=True)
async def setup_loa(ctx):
    if ctx.guild is None or ctx.guild.id != GUILD_ID: return
    embed = discord.Embed(title="📝 Leave of Absence (LOA) Portal", description="Apply for a new Leave of Absence period.", color=discord.Color(0x0d50b8))
    embed.set_footer(text="⚙️ Rise Country Automation System")
    await ctx.send(embed=embed, view=LOAButtonView())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    if not check_expired_loa.is_running():
        check_expired_loa.start()
    scheduler.start()

# Masukkan Token Bot Anda di bawah ini
bot.run("TOKEN_BOT_KAMU")
