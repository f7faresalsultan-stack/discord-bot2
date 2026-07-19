import os
import asyncio
import discord
import aiosqlite

from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("BOT_TOKEN")

GUILD_ID = 123456789012345678
CATEGORY_ID = 123456789012345678
SUPPORT_ROLE_ID = 123456789012345678
LOG_CHANNEL_ID = 123456789012345678

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ==========================
# Database
# ==========================

async def setup_database():
    async with aiosqlite.connect("tickets.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                user_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL
            )
        """)
        await db.commit()


async def get_ticket(user_id: int):
    async with aiosqlite.connect("tickets.db") as db:
        cursor = await db.execute(
            "SELECT channel_id FROM tickets WHERE user_id = ?",
            (user_id,)
        )
        data = await cursor.fetchone()
        return data


async def add_ticket(user_id: int, channel_id: int):
    async with aiosqlite.connect("tickets.db") as db:
        await db.execute(
            "INSERT OR REPLACE INTO tickets (user_id, channel_id) VALUES (?, ?)",
            (user_id, channel_id)
        )
        await db.commit()


async def remove_ticket(user_id: int):
    async with aiosqlite.connect("tickets.db") as db:
        await db.execute(
            "DELETE FROM tickets WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()

# ==========================
# Ticket Button
# ==========================

class TicketView(discord.ui.View):
    def init(self):
        super().init(timeout=None)

    @discord.ui.button(
        label="🎫 فتح تذكرة",
        style=discord.ButtonStyle.green,
        custom_id="create_ticket"
    )
    async def create_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        # التحقق من وجود تذكرة مسبقًا
        if await get_ticket(interaction.user.id):
            await interaction.response.send_message(
                "❌ لديك تذكرة مفتوحة بالفعل.",
                ephemeral=True
            )
            return

        guild = interaction.guild
        category = guild.get_channel(CATEGORY_ID)

        support_role = guild.get_role(SUPPORT_ROLE_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            support_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
        }

        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        await add_ticket(interaction.user.id, channel.id)

        await channel.send(
    f"{interaction.user.mention} مرحبًا بك.\n"
    "يرجى شرح مشكلتك وسيقوم فريق الدعم بالرد عليك.",
    view=CloseTicketView()
)
# ==========================
# Ticket Panel Command
# ==========================

@tree.command(
    name="panel",
    description="إرسال لوحة التذاكر",
    guild=discord.Object(id=GUILD_ID)
)
@app_commands.checks.has_permissions(administrator=True)
async def panel(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🎫 نظام التذاكر",
        description=(
            "مرحبًا بك!\n\n"
            "اضغط على الزر بالأسفل لفتح تذكرة.\n"
            "يرجى عدم فتح أكثر من تذكرة لنفس السبب."
        ),
        color=discord.Color.blurple()
    )

    embed.set_footer(text="Ticket System")

    await interaction.channel.send(
        embed=embed,
        view=TicketView()
    )

    await interaction.response.send_message(
        "✅ تم إرسال لوحة التذاكر.",
        ephemeral=True
    )


@panel.error
async def panel_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ هذا الأمر للإدارة فقط.",
            ephemeral=True
        )


@bot.event
async def on_ready():
    await setup_database()

    bot.add_view(TicketView())

    try:
        synced = await tree.sync(
            guild=discord.Object(id=GUILD_ID)
        )
        print(f"تم مزامنة {len(synced)} أمر.")
    except Exception as e:
        print(e)

    print(f"Logged in as {bot.user}")

# ==========================
# Confirm Close View
# ==========================

class ConfirmCloseView(discord.ui.View):
    def init(self):
        super().init(timeout=60)

    @discord.ui.button(
        label="✅ نعم، أغلق التذكرة",
        style=discord.ButtonStyle.red,
        custom_id="confirm_close_ticket"
    )
    async def confirm_close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        async with aiosqlite.connect("tickets.db") as db:
            cursor = await db.execute(
                "SELECT user_id FROM tickets WHERE channel_id = ?",
                (interaction.channel.id,)
            )

            data = await cursor.fetchone()

            if data:
                await db.execute(
                    "DELETE FROM tickets WHERE channel_id = ?",
                    (interaction.channel.id,)
                )
                await db.commit()

        await interaction.response.send_message(
            "🔒 سيتم إغلاق التذكرة خلال 5 ثوانٍ..."
        )

        await asyncio.sleep(5)

        await interaction.channel.delete()

    @discord.ui.button(
        label="❌ إلغاء",
        style=discord.ButtonStyle.gray,
        custom_id="cancel_close_ticket"
    )
    async def cancel_close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.edit_message(
            content="✅ تم إلغاء عملية الإغلاق.",
            view=None
        )

bot.run(TOKEN)
