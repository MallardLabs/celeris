from discord.ext import commands
import discord
from discord import app_commands
from helpers.embed_helpers import (
    create_basic_embed, 
    create_error_embed, 
    create_success_embed,
    calculate_schedule_progress
)
from typing import Optional, List
from models.database import Organization, OrganizationMember, PaymentSchedule, IntervalType, PaymentScheduleMember
from datetime import datetime, timedelta
import asyncio

class MainView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

        # Main menu buttons
        org_manager_btn = discord.ui.Button(
            label="Organization Manager",
            style=discord.ButtonStyle.primary,
            emoji="🏢",
            custom_id="org_manager"
        )
        payment_manager_btn = discord.ui.Button(
            label="Payment Manager",
            style=discord.ButtonStyle.primary,
            emoji="💰",
            custom_id="payment_manager"
        )
        help_btn = discord.ui.Button(
            label="Help & Commands",
            style=discord.ButtonStyle.secondary,
            emoji="❔",
            custom_id="help"
        )

        self.add_item(org_manager_btn)
        self.add_item(payment_manager_btn)
        self.add_item(help_btn)

        org_manager_btn.callback = self.org_manager_callback
        payment_manager_btn.callback = self.payment_manager_callback
        help_btn.callback = self.help_callback

    async def org_manager_callback(self, interaction: discord.Interaction):
        embed = discord.Embed(color=0x2B2D31)
        embed.title = "Organization Manager"
        embed.description = (
            "Create and manage your organizations\n\n"
            "**Available Commands**\n"
            "• `/org create` - Create a new organization\n"
            "• `/org invite` - Invite members to your organization\n"
            "• `/org kick` - Remove members from your organization\n"
            "• `/org transfer` - Transfer organization ownership\n"
            "• `/pay_org` - Create automated payments for your organization"
        )
        embed.set_footer(text="☁ Celeris runs securely on Mallard Cloud")
        
        await interaction.response.edit_message(
            embed=embed,
            view=OrganizationManagerView(self.bot)
        )

    async def payment_manager_callback(self, interaction: discord.Interaction):
        embed = discord.Embed(color=0x2B2D31)
        embed.title = "Payment Manager"
        embed.description = (
            "Manage payment schedules and view history\n\n"
            "**Available Commands**\n"
            "• `/pay` - Create individual payment schedule\n"
            "• `/pay_org` - Create organization payment schedule\n"
            "• `/schedule list` - View your active schedules\n"
            "• `/schedule cancel` - Cancel a payment schedule"
        )
        embed.set_footer(text="☁ Celeris runs securely on Mallard Cloud")
        
        await interaction.response.edit_message(
            embed=embed,
            view=PaymentManagerView(self.bot)
        )

    async def help_callback(self, interaction: discord.Interaction):
        embed = discord.Embed(color=0x2B2D31)
        embed.title = "Available Commands"
        embed.description = (
            "Here are all available commands:\n\n"
            "**Payment Commands**\n"
            "• `/pay @user <amount> <interval> <total>` - Create individual payment schedule\n"
            "• `/pay_org <org> <amount> <interval> <total>` - Create organization payment schedule\n"
            "• `/cancel_schedule <id>` - Cancel a payment schedule\n\n"
            "**Organization Commands**\n"
            "• `/org create <name>` - Create a new organization\n"
            "• `/org invite @user` - Invite someone to your organization\n"
            "• `/org kick @user` - Remove someone from your organization"
        )
        embed.set_footer(text="☁ Celeris runs securely on Mallard Cloud")
        
        await interaction.response.edit_message(embed=embed, view=self)

class OrganizationManagerView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

        create_org_btn = discord.ui.Button(
            label="Create Organization",
            style=discord.ButtonStyle.success,
            emoji="➕",
            custom_id="create_org"
        )
        my_orgs_btn = discord.ui.Button(
            label="My Organizations",
            style=discord.ButtonStyle.primary,
            emoji="📋",
            custom_id="my_orgs"
        )
        back_btn = discord.ui.Button(
            label="Back",
            style=discord.ButtonStyle.secondary,
            emoji="⬅️",
            custom_id="back"
        )

        self.add_item(create_org_btn)
        self.add_item(my_orgs_btn)
        self.add_item(back_btn)

        create_org_btn.callback = self.create_org_callback
        my_orgs_btn.callback = self.my_orgs_callback
        back_btn.callback = self.back_callback

    async def create_org_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CreateOrgModal(self.bot))

    async def my_orgs_callback(self, interaction: discord.Interaction):
        session = self.bot.db_manager.Session()
        try:
            orgs = session.query(Organization).join(
                OrganizationMember,
                Organization.id == OrganizationMember.organization_id
            ).filter(
                (Organization.owner_id == str(interaction.user.id)) |
                (OrganizationMember.user_id == str(interaction.user.id))
            ).all()

            embed = discord.Embed(color=0x2B2D31)
            embed.title = "My Organizations"

            if not orgs:
                embed.description = (
                    "You are not a member of any organizations.\n\n"
                    "**Getting Started**\n"
                    "• Use `/org create` to create a new organization\n"
                    "• Wait for organization invites to join existing ones"
                )
            else:
                embed.description = (
                    "Here are your organizations:\n\n"
                    "**Available Commands**\n"
                    "• `/pay_org` - Create automated payments\n"
                    "• `/org invite` - Invite new members\n"
                    "• `/org kick` - Remove members\n"
                    "• `/org transfer` - Transfer ownership\n"
                )
                for org in orgs:
                    member_count = session.query(OrganizationMember)\
                        .filter_by(organization_id=org.id).count()
                    is_owner = org.owner_id == str(interaction.user.id)
                    embed.add_field(
                        name=f"{'👑' if is_owner else '👤'} {org.name}",
                        value=(
                            f"Members: {member_count}\n"
                            f"Role: {'Owner' if is_owner else 'Member'}\n"
                            f"ID: #{org.id}"
                        ),
                        inline=False
                    )

            embed.set_footer(text="☁ Celeris runs securely on Mallard Cloud")
            await interaction.response.edit_message(embed=embed, view=self)

        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description=f"Failed to fetch organizations: {str(e)}",
                color=discord.Color.red()
            )
            embed.set_footer(text="☁ Celeris runs securely on Mallard Cloud")
            await interaction.response.edit_message(embed=embed, view=self)
        finally:
            session.close()

    async def back_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=create_basic_embed(
                title="Main Menu",
                description="Select an option below:"
            ),
            view=MainView(self.bot)
        )

class CreateOrgModal(discord.ui.Modal, title="Create Organization"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    org_name = discord.ui.TextInput(
        label="Organization Name",
        placeholder="Enter the name for your organization",
        min_length=3,
        max_length=50,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        session = self.bot.db_manager.Session()
        try:
            # Check if organization name already exists
            existing_org = session.query(Organization).filter_by(name=self.org_name.value).first()
            if existing_org:
                await interaction.response.send_message(
                    embed=create_error_embed(
                        title="Organization Exists",
                        description=f"An organization named '{self.org_name.value}' already exists."
                    ),
                    ephemeral=True
                )
                return

            # Create new organization
            new_org = Organization(
                name=self.org_name.value,
                owner_id=str(interaction.user.id),
                created_at=datetime.utcnow()
            )
            session.add(new_org)
            session.flush()  # Get the organization ID

            # Add owner as member
            member = OrganizationMember(
                organization_id=new_org.id,
                user_id=str(interaction.user.id),
                joined_at=datetime.utcnow()
            )
            session.add(member)
            session.commit()

            await interaction.response.send_message(
                embed=create_success_embed(
                    title="Organization Created",
                    description=f"Successfully created organization '{self.org_name.value}'!"
                ),
                ephemeral=True
            )

        except Exception as e:
            session.rollback()
            await interaction.response.send_message(
                embed=create_error_embed(
                    title="Error",
                    description=f"Failed to create organization: {str(e)}"
                ),
                ephemeral=True
            )
        finally:
            session.close()

class PaymentManagerView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

        back_btn = discord.ui.Button(
            label="Back",
            style=discord.ButtonStyle.secondary,
            emoji="⬅️",
            custom_id="back"
        )
        self.add_item(back_btn)
        back_btn.callback = self.back_callback

    async def back_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=create_basic_embed(
                title="Main Menu",
                description="Select an option below:"
            ),
            view=MainView(self.bot)
        )

class Menu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.payment_task = bot.loop.create_task(self.process_payments())

    @app_commands.command(name="start", description="Get started with Celeris")
    async def menu(self, interaction: discord.Interaction):
        embed = discord.Embed(color=0x2B2D31)  # Dark theme color
        embed.title = "Welcome to Celeris"
        embed.description = "Get Started\n\nCreate and manage organizations, automate payments, and more!"
        
        # Key Features section
        embed.add_field(
            name="🔑 Key Features",
            value="• Create organizations\n• Set up automated payments\n• Manage members and roles\n• Track payment history",
            inline=False
        )
        
        # Quick Start section
        embed.add_field(
            name="💡 Quick Start",
            value="Click 'Create Organization' to begin!",
            inline=False
        )
        
        # Add the Celeris image
        embed.set_image(url="attachment://celeris.png")
        
        # Add footer
        embed.set_footer(text="☁ Celeris runs securely on Mallard Cloud")
        
        # Create file object for the image
        file = discord.File("celeris.png", filename="celeris.png")
        
        await interaction.response.send_message(
            file=file,
            embed=embed,
            view=MainView(self.bot),
            ephemeral=True
        )

    async def process_payments(self):
        while True:
            try:
                current_time = datetime.utcnow()
                session = self.bot.db_manager.Session()

                # Process individual payments
                individual_schedules = session.query(PaymentSchedule)\
                    .join(PaymentScheduleMember)\
                    .filter(
                        PaymentSchedule.organization_id.is_(None),
                        PaymentSchedule.points_paid < PaymentSchedule.total_points
                    ).all()

                for schedule in individual_schedules:
                    # Calculate time since last payment
                    time_since_last = current_time - schedule.last_paid_at
                    interval_seconds = schedule.interval_value
                    
                    # Convert interval to seconds
                    if schedule.interval_type == IntervalType.MINUTES:
                        interval_seconds *= 60
                    elif schedule.interval_type == IntervalType.HOURS:
                        interval_seconds *= 3600
                    elif schedule.interval_type == IntervalType.DAYS:
                        interval_seconds *= 86400
                    elif schedule.interval_type == IntervalType.MONTHS:
                        interval_seconds *= 2592000  # 30 days approximation

                    if time_since_last.total_seconds() >= interval_seconds:
                        members = session.query(PaymentScheduleMember)\
                            .filter_by(schedule_id=schedule.id)\
                            .all()

                        for member in members:
                            try:
                                # Check if we've reached total points
                                if schedule.points_paid >= schedule.total_points:
                                    continue

                                # Calculate remaining points
                                remaining = schedule.total_points - schedule.points_paid
                                payment_amount = min(schedule.amount, remaining)

                                # Process the payment
                                success = await self.bot.points_manager.add_points(
                                    user_id=int(member.user_id),
                                    amount=payment_amount
                                )

                                if success:
                                    # Update schedule
                                    schedule.points_paid += payment_amount
                                    schedule.last_paid_at = current_time
                                    
                                    # Send DM notification
                                    try:
                                        user = await self.bot.fetch_user(int(member.user_id))
                                        progress, progress_bar = calculate_schedule_progress(
                                            schedule.points_paid,
                                            schedule.total_points
                                        )

                                        embed = create_success_embed(
                                            title="Payment Received",
                                            description=(
                                                "**Individual Payment**\n"
                                                "You've received a scheduled payment!\n\n"
                                                f"💰 **Amount Received**\n{payment_amount:,} points\n\n"
                                                f"📊 **Schedule Progress**\n{progress_bar} {progress:.1f}%\n"
                                                f"({schedule.points_paid}/{schedule.total_points} points)\n\n"
                                                f"⏰ **Payment Details**\n"
                                                f"• Frequency: Every {schedule.interval_value} {schedule.interval_type.value}\n"
                                                f"• Schedule ID: #{schedule.id}\n\n"
                                                f"👤 Individual Payment • Automated Payment"
                                            )
                                        )
                                        embed.set_footer(text="☁ Celeris runs securely on Mallard Cloud")
                                        await user.send(embed=embed)
                                    except Exception as e:
                                        print(f"Failed to send DM to {member.user_id}: {e}")

                                    session.commit()

                            except Exception as e:
                                print(f"Failed to process payment for {member.user_id}: {e}")
                                session.rollback()
                                continue

                # Small sleep between iterations to prevent CPU overload
                await asyncio.sleep(0.1)

            except Exception as e:
                print(f"Error in payment processing: {e}")
            finally:
                if session:
                    session.close()

    @app_commands.command(
        name="pay",
        description="Create an automated payment schedule for a user"
    )
    @app_commands.describe(
        user="The user to pay",
        amount="Amount of points per payment",
        interval_value="How often to make payments (e.g., 24)",
        interval_type="Time unit for interval (s/m/h/d/mm)",
        total_points="Total points to distribute over time"
    )
    async def pay_user(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: int,
        interval_value: int,
        interval_type: str,
        total_points: int
    ):
        # Defer the response since this might take a while
        await interaction.response.defer(ephemeral=True)
        
        # Input validation
        if amount <= 0:
            await interaction.followup.send(
                embed=create_error_embed(
                    title="Invalid Amount",
                    description="Amount must be greater than 0!"
                ),
                ephemeral=True
            )
            return

        if interval_value <= 0:
            await interaction.followup.send(
                embed=create_error_embed(
                    title="Invalid Interval",
                    description="Interval value must be greater than 0!"
                ),
                ephemeral=True
            )
            return

        if total_points <= 0:
            await interaction.followup.send(
                embed=create_error_embed(
                    title="Invalid Total",
                    description="Total points must be greater than 0!"
                ),
                ephemeral=True
            )
            return

        if total_points < amount:
            await interaction.followup.send(
                embed=create_error_embed(
                    title="Invalid Amount",
                    description="Total points must be greater than or equal to amount per payment!"
                ),
                ephemeral=True
            )
            return

        # Validate interval type
        try:
            interval_type = IntervalType(interval_type.lower())
        except ValueError:
            await interaction.followup.send(
                embed=create_error_embed(
                    title="Invalid Interval Type",
                    description="Valid interval types are: s (seconds), m (minutes), h (hours), d (days), mm (months)"
                ),
                ephemeral=True
            )
            return

        session = self.bot.db_manager.Session()
        try:
            # Create payment schedule
            schedule = PaymentSchedule(
                amount=amount,
                interval_type=interval_type,
                interval_value=interval_value,
                total_points=total_points,
                points_paid=0,
                created_by=str(interaction.user.id),
                last_paid_at=datetime.utcnow()
            )
            session.add(schedule)
            session.flush()  # Get the schedule ID

            # Add schedule member
            schedule_member = PaymentScheduleMember(
                schedule_id=schedule.id,
                user_id=str(user.id)
            )
            session.add(schedule_member)

            # Calculate schedule details
            total_payments = total_points // amount
            remaining = total_points % amount
            duration = interval_value * total_payments

            # Convert duration to human-readable format
            duration_str = ""
            if interval_type == IntervalType.SECONDS:
                duration_str = f"{duration} seconds"
            elif interval_type == IntervalType.MINUTES:
                duration_str = f"{duration} minutes"
            elif interval_type == IntervalType.HOURS:
                duration_str = f"{duration} hours"
            elif interval_type == IntervalType.DAYS:
                duration_str = f"{duration} days"
            elif interval_type == IntervalType.MONTHS:
                duration_str = f"{duration} months"

            # Make initial payment
            try:
                success = await self.bot.points_manager.add_points(user.id, amount)
                if success:
                    schedule.points_paid += amount
                    
                    # Send DM notification to recipient
                    try:
                        progress, progress_bar = calculate_schedule_progress(amount, total_points)
                        recipient_embed = create_success_embed(
                            title="Payment Schedule Created",
                            description=(
                                f"**{interaction.user.name}** has created a payment schedule for you!\n\n"
                                f"💰 **Amount per Payment:** {amount:,} points\n"
                                f"⏰ **Frequency:** Every {interval_value} {interval_type.value}\n"
                                f"📊 **Progress:** {progress_bar} {progress:.1f}%\n"
                                f"💵 **Total Points:** {total_points:,}\n"
                                f"🔄 **Duration:** {duration_str}\n"
                                f"🆔 **Schedule ID:** #{schedule.id}"
                            )
                        )
                        await user.send(embed=recipient_embed)
                    except Exception as e:
                        print(f"Failed to send DM to recipient: {e}")

            except Exception as e:
                print(f"Failed to make initial payment: {e}")

            session.commit()

            # Send confirmation to command user
            embed = create_success_embed(
                title="Payment Schedule Created",
                description=(
                    f"Created payment schedule for {user.mention}!\n\n"
                    "**📊 Schedule Details**\n"
                    f"• Amount per payment: {amount:,} points\n"
                    f"• Interval: Every {interval_value} {interval_type.value}\n"
                    f"• Total points: {total_points:,}\n"
                    f"• Number of payments: {total_payments}\n"
                    f"• Duration: {duration_str}\n"
                    f"• Schedule ID: #{schedule.id}\n\n"
                    "**💰 Initial Payment**\n"
                    f"• Status: {'✅ Sent' if success else '❌ Failed'}\n"
                    f"• Amount: {amount:,} points"
                )
            )
            embed.set_footer(text="☁ Celeris runs securely on Mallard Cloud")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            session.rollback()
            await interaction.followup.send(
                embed=create_error_embed(
                    title="Error",
                    description=f"Failed to create payment schedule: {str(e)}"
                ),
                ephemeral=True
            )
        finally:
            session.close()

async def setup(bot):
    await bot.add_cog(Menu(bot)) 
