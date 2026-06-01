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

# ====================================================================
# CONFIGURATION
# ====================================================================
ID_CHANNEL_LOG_LOA = 1510642659776266442  # Ganti dengan ID Channel Admin kamu
ID_ROLE_LOA = 1469270847905730590         # Ganti dengan ID Role LOA kamu
GUILD_ID = 1351182942625337378            # Ganti dengan ID Server (Guild) kamu
DATA_FILE = "loa_data.json"

# ====================================================================
# SAKELAR SISTEM LOA (GLOBAL STATE)
# True = Aktif (Menerima LOA), False = Nonaktif (LOA Ditutup)
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
    
    # List untuk menampung ID yang sudah kedaluwarsa
    expired_members = []

    for member_id_str, details in list(loa_data.items()):
        try:
            # Parse tanggal selesai (Format: DD/MM/YYYY)
            end_date = datetime.strptime(details["end_date"], "%d/%m/%Y")
            
            # Jika hari ini sudah melewati tanggal selesai LOA
            if now.date() > end_date.date():
                member_id = int(member_id_str)
                member = guild.get_member(member_id)
                
                if member and role_loa in member.roles:
                    try:
                        await member.remove_roles(role_loa)
                        # Kirim DM Otomatis ke member
                        embed_dm = discord.Embed(
                            title="Notice of LOA Termination",
                            description=f"Hello {member.mention},\n\nThis is an official automated notification to inform you that your Leave of Absence (LOA) period has concluded. Your LOA role has been removed, and you are expected to resume your standard duties and responsibilities.",
                            color=discord.Color(0x0d50b8)
                        )
                        embed_dm.set_footer(text="Thank you for your cooperation and welcome back.")
                        await member.send(embed=embed_dm)
                    except Exception as e:
                        print(f"Failed to remove role or DM member {member_id}: {e}")
                
                # Kirim log ke channel admin bahwa LOA telah selesai otomatis
                log_channel = bot.get_channel(ID_CHANNEL_LOG_LOA)
                if log_channel:
                    await log_channel.send(f"Automated System: LOA period has concluded for <@{member_id_str}>. Role removed.")

                del loa_data[member_id_str]
                updated = True
        except ValueError:
            # Jika format tanggal salah di database, abaikan agar tidak crash
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
            
            # SIMPAN KE DATABASE OTOMATIS
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
# MODAL: FORMULIR LOA (MAKSIMAL 5 INPUT)
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
        
        # Validasi format tanggal masukan user agar sistem tidak error
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

# ====================================================================
# VIEW: MAIN SYSTEM TOMBOL "CREATE LOA"
# ====================================================================
class LOAButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create LOA", style=discord.ButtonStyle.secondary, custom_id="button_create_loa")
    async def create_loa_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # PENGECEKAN STATUS SAKELAR GLOBAL SEBELUM FORMULIR DIKIRIM
        if not loa_system_active:
            return await interaction.response.send_message(
                "🔒 **Sorry, the LOA Submission System is currently disabled by the Administration.** Please try again later.", 
                ephemeral=True
            )
        await interaction.response.send_modal(LOAForm())

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
        await ctx.send("The LOA system has been disabled.")
    elif status.lower() == "on":
        loa_system_active = True
        await ctx.send("The LOA system has been enabled.")
    else:
        await ctx.send("❌ Invalid format. Use `!loasystem on` or `!loasystem off`.")

@toggle_loa_system.error
async def loasystem_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You do not have the required permissions (Administrator) to toggle the LOA system status.")

# ====================================================================
# MAIN APPLICATION EVENTS
# ====================================================================
@bot.event
async def on_ready():
    bot.add_view(LOAButtonView())
    # Hidupkan sistem pengecekan otomatis jam
    if not check_expired_loa.is_running():
        check_expired_loa.start()
    print(f"System Active! {bot.user} is fully automated with database tracking.")

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
    
    embed = discord.Embed(
        title="Leave of Absence (LOA) Portal",
        description=desc_text,
        color=discord.Color(0x0d50b8)
    )
    await ctx.send(embed=embed, view=LOAButtonView())

# Perintah manual darurat (jika admin ingin mencopot role LOA instan sebelum waktunya)
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
    else:
        await ctx.send("Member doesn't have LOA role.")

bot.run(os.getenv('DISCORD_TOKEN'))
