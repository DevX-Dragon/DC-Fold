import discord

class DeploymentConfirmationView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=60.0)
        self.owner_id = owner_id
        self.action_choice = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ Only the Server Owner can interact with these deployment systems.", 
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Wipe & Deploy", style=discord.ButtonStyle.danger, custom_id="confirm_wipe")
    async def confirm_wipe(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.action_choice = "wipe"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Keep Existing & Deploy", style=discord.ButtonStyle.primary, custom_id="confirm_keep")
    async def confirm_keep(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.action_choice = "keep"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel Setup", style=discord.ButtonStyle.secondary, custom_id="cancel_deploy")
    async def cancel_deploy(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.action_choice = "cancel"
        self.stop()
        await interaction.response.defer()