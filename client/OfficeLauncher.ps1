# Desktop launcher: shows the programs in O:\_Програми as tiles for the logged-in Windows user. Windows only needs PowerShell.
param([string]$Root = 'O:\_Програми', [string]$Portal = 'https://office-server', [string]$Shot)
Add-Type -AssemblyName PresentationFramework, System.Drawing
$ext = '.exe', '.lnk', '.bat', '.cmd', '.accdb', '.mdb'

# Self-update: the server holds the newest copy; if it is newer, replace this file and start again.
$new = Join-Path (Split-Path $Root) '_launcher\OfficeLauncher.ps1'
if (-not $Shot -and $PSCommandPath -and (Test-Path -LiteralPath $new) -and
    (Get-Item -LiteralPath $new).LastWriteTime -gt (Get-Item -LiteralPath $PSCommandPath).LastWriteTime) {
  try {
    Copy-Item -LiteralPath $new -Destination $PSCommandPath -Force
    Start-Process powershell -ArgumentList '-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`""
    exit
  } catch {}
}

function Get-Apps {
  if (-not (Test-Path -LiteralPath $Root)) { return @() }
  # Unreadable folders are skipped silently: the share's own rights decide what each user sees.
  $f = Get-ChildItem -LiteralPath $Root -File -ErrorAction SilentlyContinue
  $f += Get-ChildItem -LiteralPath $Root -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch '^[_.]' } |
    ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -File -ErrorAction SilentlyContinue }
  $f | Where-Object { $ext -contains $_.Extension.ToLower() -and $_.Name -notmatch 'unins' -and $_.Name -notmatch '^[_.]' } |
    Select-Object -First 60 | Sort-Object BaseName
}

function Write-Log($m) {
  try { Add-Content -LiteralPath "$env:LOCALAPPDATA\OfficeApp\launcher.log" -Value "$(Get-Date -Format s) $m" } catch {}
}

# A .lnk on the share is read here ourselves: Shell.Application handles Unicode paths, and Windows does not resolve network shortcuts for icons.
function Resolve-Lnk($path) {
  try {
    $lk = (New-Object -ComObject Shell.Application).NameSpace((Split-Path $path)).ParseName((Split-Path $path -Leaf)).GetLink
    if ($lk.Path -and (Test-Path -LiteralPath $lk.Path)) { @{ Path = $lk.Path; Args = $lk.Arguments } }
  } catch { Write-Log "resolve failed: $path $($_.Exception.Message)" }
}

function Get-Icon($path) {
  try {
    if ($path -like '*.lnk') { $r = Resolve-Lnk $path; if ($r) { $path = $r.Path } }
    $i = [System.Drawing.Icon]::ExtractAssociatedIcon($path)
    [System.Windows.Interop.Imaging]::CreateBitmapSourceFromHIcon($i.Handle, [System.Windows.Int32Rect]::Empty,
      [System.Windows.Media.Imaging.BitmapSizeOptions]::FromEmptyOptions())
  } catch { $null }
}

function Start-App($path) {
  try {
    $a = @{ FilePath = $path; WorkingDirectory = (Split-Path $path); ErrorAction = 'Stop' }
    if ($path -like '*.lnk') {
      $r = Resolve-Lnk $path
      if ($r) { $a.FilePath = $r.Path; $a.WorkingDirectory = Split-Path $r.Path; if ($r.Args) { $a.ArgumentList = $r.Args } }
    }
    Write-Log "start $($a.FilePath)"
    Start-Process @a
  } catch {
    Write-Log "start failed: $path $($_.Exception.Message)"
    [System.Windows.MessageBox]::Show("Cannot start $path`n`n$($_.Exception.Message)", 'Office', 'OK', 'Warning') | Out-Null
  }
}

[xml]$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Офис" Width="1000" Height="660" MinWidth="560" MinHeight="420" WindowStartupLocation="CenterScreen" FontFamily="Segoe UI">
  <Window.Background>
    <LinearGradientBrush StartPoint="0,0" EndPoint="1,1">
      <GradientStop Color="#0B1020" Offset="0"/><GradientStop Color="#1A1450" Offset="0.6"/><GradientStop Color="#3B1D6B" Offset="1"/>
    </LinearGradientBrush>
  </Window.Background>
  <Window.Resources>
    <Style x:Key="Pill" TargetType="Button">
      <Setter Property="Foreground" Value="White"/><Setter Property="Cursor" Value="Hand"/><Setter Property="Padding" Value="18,9"/>
      <Setter Property="Template"><Setter.Value>
        <ControlTemplate TargetType="Button">
          <Border x:Name="b" Background="#1FFFFFFF" CornerRadius="20" BorderBrush="#33FFFFFF" BorderThickness="1" Padding="{TemplateBinding Padding}">
            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
          </Border>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True"><Setter TargetName="b" Property="Background" Value="#6B5CF6"/></Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value></Setter>
    </Style>
    <Style x:Key="Tile" TargetType="Button">
      <Setter Property="Foreground" Value="White"/><Setter Property="Cursor" Value="Hand"/>
      <Setter Property="RenderTransformOrigin" Value="0.5,0.5"/>
      <Setter Property="RenderTransform"><Setter.Value><ScaleTransform ScaleX="1" ScaleY="1"/></Setter.Value></Setter>
      <Setter Property="Template"><Setter.Value>
        <ControlTemplate TargetType="Button">
          <Border x:Name="b" Background="#14FFFFFF" CornerRadius="22" BorderBrush="#26FFFFFF" BorderThickness="1">
            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
          </Border>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="b" Property="Background" Value="#33818CF8"/>
              <Setter TargetName="b" Property="BorderBrush" Value="#A5B4FC"/>
              <Setter Property="RenderTransform"><Setter.Value><ScaleTransform ScaleX="1.06" ScaleY="1.06"/></Setter.Value></Setter>
              <Setter TargetName="b" Property="Effect"><Setter.Value><DropShadowEffect Color="#6B5CF6" BlurRadius="30" ShadowDepth="0" Opacity="0.9"/></Setter.Value></Setter>
            </Trigger>
            <Trigger Property="IsPressed" Value="True">
              <Setter Property="RenderTransform"><Setter.Value><ScaleTransform ScaleX="0.97" ScaleY="0.97"/></Setter.Value></Setter>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value></Setter>
    </Style>
  </Window.Resources>
  <Grid Margin="36,30,36,24">
    <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
    <DockPanel Margin="0,0,0,22">
      <StackPanel DockPanel.Dock="Right" Orientation="Horizontal" VerticalAlignment="Center">
        <Button Name="Files" Content="📁  Файлове" Style="{StaticResource Pill}" Margin="0,0,8,0"/>
        <Button Name="Web" Content="🌐  Портал" Style="{StaticResource Pill}" Margin="0,0,8,0"/>
        <Button Name="Reload" Content="⟳" Style="{StaticResource Pill}"/>
      </StackPanel>
      <StackPanel Orientation="Horizontal">
        <Border Width="56" Height="56" CornerRadius="28" Margin="0,0,16,0">
          <Border.Background><LinearGradientBrush StartPoint="0,0" EndPoint="1,1"><GradientStop Color="#6366F1" Offset="0"/><GradientStop Color="#EC4899" Offset="1"/></LinearGradientBrush></Border.Background>
          <TextBlock Name="Av" FontSize="26" FontWeight="Bold" Foreground="White" HorizontalAlignment="Center" VerticalAlignment="Center"/>
        </Border>
        <StackPanel VerticalAlignment="Center">
          <TextBlock Name="Hi" FontSize="26" FontWeight="Bold" Foreground="White"/>
          <TextBlock Name="Who" FontSize="13" Foreground="#A5B4FC"/>
        </StackPanel>
      </StackPanel>
    </DockPanel>
    <Border Grid.Row="1" Background="#14FFFFFF" CornerRadius="16" BorderBrush="#26FFFFFF" BorderThickness="1" Padding="16,4" Margin="0,0,0,20">
      <DockPanel>
        <TextBlock Text="🔍" Foreground="#A5B4FC" FontSize="15" VerticalAlignment="Center" Margin="0,0,10,0"/>
        <TextBox Name="Q" Background="Transparent" BorderThickness="0" Foreground="White" CaretBrush="White" FontSize="15" Padding="0,8" VerticalContentAlignment="Center"/>
      </DockPanel>
    </Border>
    <ScrollViewer Grid.Row="2" VerticalScrollBarVisibility="Auto"><WrapPanel Name="Tiles" Margin="0,6,0,6"/></ScrollViewer>
    <TextBlock Name="Empty" Grid.Row="2" Foreground="#A5B4FC" FontSize="15" TextWrapping="Wrap" Visibility="Collapsed"/>
    <TextBlock Name="Foot" Grid.Row="3" Foreground="#818CF8" Margin="0,14,0,0"/>
  </Grid>
</Window>
'@
$w = [Windows.Markup.XamlReader]::Load((New-Object System.Xml.XmlNodeReader $xaml))
$tiles = $w.FindName('Tiles'); $empty = $w.FindName('Empty'); $q = $w.FindName('Q')
$w.FindName('Av').Text = "$env:USERNAME".Substring(0, 1).ToUpper()
$w.FindName('Hi').Text = "Здравей, $env:USERNAME"
$w.FindName('Who').Text = "$env:COMPUTERNAME  ·  свързан с офис сървъра"
$w.FindName('Files').Add_Click({ Start-Process explorer.exe ((Split-Path $Root -Qualifier) + '\') })
$w.FindName('Web').Add_Click({ Start-Process $Portal })

function Show-Apps {
  $tiles.Children.Clear()
  $apps = @(Get-Apps)
  $empty.Visibility = if ($apps.Count) { 'Collapsed' } else { 'Visible' }
  $empty.Text = if (Test-Path -LiteralPath $Root) { 'Няма програми. Администраторът ги слага в папка _Програми.' } else { 'Няма връзка със сървъра (диск O:). Стартирайте setup.cmd.' }
  $w.FindName('Foot').Text = "$($apps.Count) програми"
  foreach ($a in $apps) {
    $b = New-Object System.Windows.Controls.Button
    $b.Style = $w.FindResource('Tile'); $b.Width = 164; $b.Height = 152; $b.Margin = '0,0,16,16'
    $b.Tag = $a.FullName; $b.ToolTip = $a.FullName; $b.DataContext = $a.BaseName
    $sp = New-Object System.Windows.Controls.StackPanel
    $img = New-Object System.Windows.Controls.Image; $img.Width = 60; $img.Height = 60; $img.Source = Get-Icon $a.FullName
    $t = New-Object System.Windows.Controls.TextBlock
    $t.Text = $a.BaseName; $t.TextWrapping = 'Wrap'; $t.TextAlignment = 'Center'; $t.Margin = '10,12,10,0'; $t.FontWeight = 'SemiBold'; $t.FontSize = 14
    $sp.Children.Add($img) | Out-Null; $sp.Children.Add($t) | Out-Null; $b.Content = $sp
    $b.Add_Click({
      try { Start-App $this.Tag }
      catch { Write-Log "click failed: $($_.Exception.Message)"; [System.Windows.MessageBox]::Show($_.Exception.Message, 'Office') | Out-Null }
    })
    $tiles.Children.Add($b) | Out-Null
  }
}
$q.Add_TextChanged({
  foreach ($b in $tiles.Children) { $b.Visibility = if ($b.DataContext -like "*$($q.Text)*") { 'Visible' } else { 'Collapsed' } }
})
$w.FindName('Reload').Add_Click({ Show-Apps })
Show-Apps
if ($Shot) {   # test hook: render the window to a PNG and quit
  $w.Add_ContentRendered({
    $r = New-Object System.Windows.Media.Imaging.RenderTargetBitmap ([int]$w.ActualWidth), ([int]$w.ActualHeight), 96, 96, ([System.Windows.Media.PixelFormats]::Pbgra32)
    $r.Render($w)
    $e = New-Object System.Windows.Media.Imaging.PngBitmapEncoder; $e.Frames.Add([System.Windows.Media.Imaging.BitmapFrame]::Create($r))
    $s = [IO.File]::Create($Shot); $e.Save($s); $s.Close(); $w.Close()
  })
}
$q.Focus() | Out-Null
$w.ShowDialog() | Out-Null
