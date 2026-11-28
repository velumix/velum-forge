--!nocheck
--[[
	Velum Forge - generated Studio setup for "__ASSET__" (tools/blender/sclib/export.py).
	DO NOT EDIT BY HAND: re-export from Blender instead.

	1. Import __ASSET__.fbx with the 3D Importer (File Dimensions: Studs) into Workspace.
	2. Select the imported Model.
	3. Paste this whole file into the Command Bar and press Enter (or run it through the
	   Roblox Studio MCP `execute_luau` tool). Re-running is safe: it replaces what it created.

	Optional: upload the three palette PNGs (textures/) and paste their asset ids below to give
	every "solid" part a SurfaceAppearance with roughness/metalness. Without ids the importer's
	colour TextureID is kept.
]]
local TEXTURE_IDS = {
	Color = "", -- rbxassetid://...  (__ASSET__ ColorMap PNG)
	Normal = "", -- rbxassetid://...  (__ASSET__ NormalMap OpenGL PNG)
	Roughness = "", -- rbxassetid://...  (__ASSET__ RoughnessMap PNG)
	Metalness = "", -- rbxassetid://...  (__ASSET__ MetalnessMap PNG)
}

-- Optional per-texture-set SurfaceAppearance overrides for multi-set 2K scenes:
local TEXTURE_SETS = __TEXTURE_SETS__

local HttpService = game:GetService("HttpService")
local CollectionService = game:GetService("CollectionService")
local Selection = game:GetService("Selection")
local ChangeHistoryService = game:GetService("ChangeHistoryService")

local M = HttpService:JSONDecode([==[
__MANIFEST__
]==])

local function v3(t)
	return Vector3.new(t[1], t[2], t[3])
end

local model = Selection:Get()[1]
if model and not model:IsA("Model") then
	model = model:FindFirstAncestorWhichIsA("Model")
end
assert(model, "[sclib] Select the imported " .. M.asset .. " model first")

local recording = ChangeHistoryService:TryBeginRecording("sclib setup " .. M.asset)

local function mark(inst)
	inst:SetAttribute("sclibGenerated", true)
	return inst
end

local function clearGenerated(root)
	for _, d in root:GetDescendants() do
		if d:GetAttribute("sclibGenerated") then
			d:Destroy()
		end
	end
end
clearGenerated(model)

-- Index imported mesh parts (the importer may nest them; earlier runs may have renamed them).
local renamedFrom = {}
for original, info in M.parts do
	if info.rename then
		renamedFrom[info.rename] = original
	end
end
local parts = {}
for _, d in model:GetDescendants() do
	if d:IsA("BasePart") then
		local key = if M.parts[d.Name] then d.Name else renamedFrom[d.Name]
		if key and not parts[key] then
			parts[key] = d
		end
	end
end
for name in M.parts do
	if not parts[name] then
		warn("[sclib] missing imported part: " .. name)
	end
end

-- Solve the asset frame & uniform scale: which of the 24 axis-aligned rotations maps manifest centres onto
-- the imported parts (even when the user scaled the imported Model in Studio).
local ref = parts[M.reference]
assert(ref, "[sclib] reference part missing: " .. M.reference)
local refC = v3(M.parts[M.reference].center)
local axes = { Vector3.xAxis, -Vector3.xAxis, Vector3.yAxis, -Vector3.yAxis, Vector3.zAxis, -Vector3.zAxis }
local best, bestErr, bestScale = CFrame.identity, math.huge, 1
for _, x in axes do
	for _, y in axes do
		if math.abs(x:Dot(y)) < 0.5 then
			local R = CFrame.fromMatrix(Vector3.zero, x, y)
			local sNum, sDen = 0, 0
			for name, p in parts do
				local m = R:VectorToWorldSpace(v3(M.parts[name].center) - refC)
				local w = p.Position - ref.Position
				sNum += w:Dot(m)
				sDen += m:Dot(m)
			end
			local scale = if sDen > 1e-6 then sNum / sDen else 1
			if scale > 0.05 then
				local err = 0
				for name, p in parts do
					local m = R:VectorToWorldSpace(v3(M.parts[name].center) - refC) * scale
					local w = p.Position - ref.Position
					err += (w - m).Magnitude
				end
				if err < bestErr - 1e-3 then
					bestErr, best, bestScale = err, R, scale
				end
			end
		end
	end
end

local function toWorld(p)
	return ref.Position + best:VectorToWorldSpace((v3(p) - refC) * bestScale)
end
local function frameOf(s)
	local pos = toWorld(s.position)
	return CFrame.lookAt(pos, pos + best:VectorToWorldSpace(v3(s.look)), best:VectorToWorldSpace(v3(s.up)))
end
local function hingeFrame(s, invertAxis) -- attachment PrimaryAxis (X) = socket up = hinge axis
	local axis = best:VectorToWorldSpace(v3(s.up))
	if invertAxis then
		axis = -axis
	end
	return CFrame.fromMatrix(toWorld(s.position), axis, best:VectorToWorldSpace(v3(s.look)))
end

-- PrimaryPart (invisible hull box: X = beam, Z = length, scaled to match imported model)
local primary = model:FindFirstChild(M.primary.name)
if not (primary and primary:IsA("BasePart")) then
	primary = Instance.new("Part")
	primary.Name = M.primary.name
end
primary.Size = v3(M.primary.size) * bestScale
primary.CFrame = frameOf(M.primary)
primary.Transparency = 1
primary.CanCollide = false
primary.CanTouch = false
primary.CanQuery = false
primary.CastShadow = false
primary.Massless = false
primary.CustomPhysicalProperties = PhysicalProperties.new(0.7, 0.25, 0.05, 1.0, 1.0)
primary.Anchored = true
primary.TopSurface = Enum.SurfaceType.Smooth
primary.BottomSurface = Enum.SurfaceType.Smooth
primary.Parent = model
model.PrimaryPart = primary

-- Hinged parts are driven by constraints, never welded.
local hinged = {}
for _, h in M.hinges do
	hinged[h.part1] = true
end

local useSurfaceAppearance = TEXTURE_IDS.Color ~= ""
for name, info in M.parts do
	local p = parts[name]
	if not p then
		continue
	end
	local setIds = (info.texture_set and TEXTURE_SETS[info.texture_set]) or nil
	local texIds = (setIds and setIds.Color and setIds.Color ~= "" and setIds) or TEXTURE_IDS
	local useSetSA = (texIds ~= nil and texIds.Color ~= nil and texIds.Color ~= "") or useSurfaceAppearance
	local isBakedRole = info.role == "solid" or string.sub(tostring(info.role or ""), 1, 6) == "baked_"
	if info.role == "glass" or info.role == "neon" then
		for _, c in p:GetChildren() do
			if c:IsA("SurfaceAppearance") then
				c:Destroy()
			end
		end
		if p:IsA("MeshPart") then
			p.TextureID = ""
		end
		p.Color = Color3.new(info.color[1], info.color[2], info.color[3])
	elseif info.role == "paint" then
		local existingSA = p:FindFirstChildWhichIsA("SurfaceAppearance")
		if not existingSA and (not p:IsA("MeshPart") or p.TextureID == "") then
			p.Color = Color3.new(info.color[1], info.color[2], info.color[3])
		end
	elseif useSetSA and isBakedRole and texIds.Color ~= "" then
		for _, c in p:GetChildren() do
			if c:IsA("SurfaceAppearance") then
				c:Destroy()
			end
		end
		local sa = mark(Instance.new("SurfaceAppearance"))
		pcall(function()
			sa.ColorMap = texIds.Color
			if texIds.Normal and texIds.Normal ~= "" then
				sa.NormalMap = texIds.Normal
			end
			if texIds.Roughness and texIds.Roughness ~= "" then
				sa.RoughnessMap = texIds.Roughness
			end
			if texIds.Metalness and texIds.Metalness ~= "" then
				sa.MetalnessMap = texIds.Metalness
			end
		end)
		sa.Parent = p
		if p:IsA("MeshPart") then
			p.TextureID = ""
		end
	end
	if info.material then
		pcall(function()
			p.Material = Enum.Material[info.material]
		end)
	end
	p.Transparency = info.transparency or 0
	p.CanCollide = (info.collide == true) and name ~= "LeaningPost"
	p.CanTouch = false
	p.CanQuery = p.CanCollide
	p.CastShadow = info.role ~= "glass" and info.role ~= "neon"
	p.Anchored = true
	p.Massless = not hinged[name]
	if hinged[name] then
		p.CustomPhysicalProperties = PhysicalProperties.new(0.25, 0.1, 0.0, 1.0, 1.0)
	end
	if p:IsA("MeshPart") then
		pcall(function()
			p.CollisionFidelity = if p.CanCollide
				then Enum.CollisionFidelity.PreciseConvexDecomposition
				else Enum.CollisionFidelity.Box
			p.RenderFidelity = if info.render_fidelity == "Precise"
				then Enum.RenderFidelity.Precise
				else Enum.RenderFidelity.Automatic
		end)
	end
	if info.group then
		local g = model:FindFirstChild(info.group)
		if not g then
			g = Instance.new("Model")
			g.Name = info.group
			g.Parent = model
		end
		p.Parent = g
	end
	if info.rename then
		p.Name = info.rename
	end
	if not hinged[name] then
		local w = mark(Instance.new("WeldConstraint"))
		w.Name = "Weld_" .. p.Name
		w.Part0 = primary
		w.Part1 = p
		w.Parent = p
	end
end

-- Attachments
local socketsByName = {}
for _, s in M.sockets do
	socketsByName[s.name] = s
	if s.hinge_only then
		continue
	end
	local host = (s.parent and parts[s.parent]) or primary
	local a = mark(Instance.new("Attachment"))
	a.Name = s.name
	a.CFrame = host.CFrame:ToObjectSpace(frameOf(s))
	a.Parent = host
	if s.emitter then
		local pe = mark(Instance.new("ParticleEmitter"))
		pe.Name = "Splash"
		pe.Enabled = true
		pe.Rate = 0
		pe.Texture = "rbxassetid://241576804"
		pe.Color = ColorSequence.new(Color3.fromRGB(238, 249, 255), Color3.fromRGB(205, 235, 250))
		pe.Lifetime = NumberRange.new(0.45, 0.85)
		pe.Speed = NumberRange.new(8, 14)
		pe.SpreadAngle = Vector2.new(18, 24)
		pe.Acceleration = Vector3.new(0, -28, 0)
		pe.Drag = 2.2
		pe.LightInfluence = 0.25
		pe.Size = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 0.55),
			NumberSequenceKeypoint.new(0.45, 1.45),
			NumberSequenceKeypoint.new(1, 2.6),
		})
		pe.Transparency = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 0.30),
			NumberSequenceKeypoint.new(0.5, 0.58),
			NumberSequenceKeypoint.new(1, 1.0),
		})
		pe.Parent = a
	end
end

-- Seats (empty marks the cushion surface; the seat part sits just below it)
for _, s in M.seats do
	local seat = mark(Instance.new(if s.driver then "VehicleSeat" else "Seat"))
	seat.Name = if s.driver then "VehicleSeat" else "Seat_" .. s.name
	seat.Size = v3(s.size)
	seat.CFrame = frameOf(s) * CFrame.new(0, -s.size[2] / 2, 0)
	seat.Transparency = 1
	seat.CanCollide = false
	seat.CanTouch = true
	seat.CanQuery = false
	seat.Massless = true
	seat.Anchored = true
	if s.driver then
		seat.MaxSpeed = M.attributes.MaxSpeed or 30
		seat.HeadsUpDisplay = false
	end
	seat.Parent = model
	local w = mark(Instance.new("WeldConstraint"))
	w.Part0 = primary
	w.Part1 = seat
	w.Parent = seat
end

-- Servos (HingeConstraints in model.Servos, names match BoatService)
local isBoat = table.find(M.tags, "Boat") ~= nil
local boatUp = if M.primary and M.primary.up then best:VectorToWorldSpace(v3(M.primary.up)) else Vector3.yAxis
local servos = model:FindFirstChild("Servos")
if not servos then
	servos = Instance.new("Folder")
	servos.Name = "Servos"
	servos.Parent = model
end
for _, h in M.hinges do
	local s = socketsByName[h.socket]
	local p0 = if h.part0 == "@primary" then primary else parts[h.part0]
	local p1 = parts[h.part1]
	if not (s and p0 and p1) then
		warn("[sclib] skipped hinge " .. h.name)
		continue
	end
	-- BoatService drives Motor.TargetAngle = -Seat.Steer * MotorMaxAngle; enforce -Y hinge axis so right steer swings prop starboard
	local invertMotorAxis = isBoat and h.name == "Motor" and best:VectorToWorldSpace(v3(s.up)):Dot(boatUp) > 0
	local cf = hingeFrame(s, invertMotorAxis)
	local a0 = mark(Instance.new("Attachment"))
	a0.Name = h.name .. "Att0"
	a0.CFrame = p0.CFrame:ToObjectSpace(cf)
	a0.Parent = p0
	local a1 = mark(Instance.new("Attachment"))
	a1.Name = h.name .. "Att1"
	a1.CFrame = p1.CFrame:ToObjectSpace(cf)
	a1.Parent = p1
	local hc = mark(Instance.new("HingeConstraint"))
	hc.Name = h.name
	hc.Attachment0 = a0
	hc.Attachment1 = a1
	if h.actuator == "Motor" then
		hc.ActuatorType = Enum.ActuatorType.Motor
		hc.MotorMaxTorque = h.torque or 1e6
		hc.MotorMaxAcceleration = math.huge
	else
		hc.ActuatorType = Enum.ActuatorType.Servo
		hc.ServoMaxTorque = h.torque or 1e6
		hc.AngularSpeed = h.speed or 4
	end
	if h.lower then
		hc.LimitsEnabled = true
		hc.LowerAngle = h.lower
		hc.UpperAngle = h.upper
	end
	hc.Parent = servos
end

for k, v in M.attributes do
	model:SetAttribute(k, v)
end
if isBoat then
	if CollectionService:HasTag(model, "Vehicle") then
		CollectionService:RemoveTag(model, "Vehicle")
	end
	pcall(function()
		model.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
	end)
end
for _, t in M.tags do
	CollectionService:AddTag(model, t)
end
model.WorldPivot = primary.CFrame

if recording then
	ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
end
local partCount = 0
for _ in parts do
	partCount += 1
end
print(
	("[sclib] %s ready: %d parts, %d attachments, %d seats, %d servos (frame fit error %.3f studs)"):format(
		M.asset,
		partCount,
		#M.sockets,
		#M.seats,
		#M.hinges,
		bestErr
	)
)

