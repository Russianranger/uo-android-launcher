using Mono.Cecil;

// Constant rows already encode an enum's underlying storage type. Preserve
// that exact type when optional-parameter enum dependencies are unavailable;
// no executable dependency substitute is generated or shipped.
sealed class ConstantMetadataResolver(IAssemblyResolver assemblies) : MetadataResolver(assemblies)
{
    readonly Dictionary<string, TypeDefinition> enums = new();
    public void Record(ModuleDefinition module)
    {
        void Add(TypeReference type, object value)
        {
            if (value == null || !type.IsValueType || type.MetadataType != MetadataType.ValueType) return;
            Type underlying = value.GetType();
            if (!(underlying == typeof(int) || underlying == typeof(uint) || underlying == typeof(byte) ||
                  underlying == typeof(sbyte) || underlying == typeof(short) || underlying == typeof(ushort) ||
                  underlying == typeof(long) || underlying == typeof(ulong))) return;
            var metadata = new TypeDefinition(type.Namespace, type.Name, TypeAttributes.Public | TypeAttributes.Sealed,
                new TypeReference("System", "Enum", module, module.TypeSystem.CoreLibrary));
            metadata.Fields.Add(new FieldDefinition("value__", FieldAttributes.Public | FieldAttributes.SpecialName | FieldAttributes.RTSpecialName,
                (TypeReference)typeof(TypeSystem).GetProperty(underlying.Name)!.GetValue(module.TypeSystem)!));
            if (enums.TryGetValue(type.FullName, out var previous) &&
                previous.Fields[0].FieldType.FullName != metadata.Fields[0].FieldType.FullName)
                throw new InvalidOperationException("Conflicting constant storage: " + type.FullName);
            enums[type.FullName] = metadata;
        }
        foreach (var type in module.GetTypes())
        {
            foreach (var method in type.Methods)
                foreach (var parameter in method.Parameters)
                    if (parameter.HasConstant) Add(parameter.ParameterType, parameter.Constant);
            foreach (var field in type.Fields)
                if (field.HasConstant) Add(field.FieldType, field.Constant);
        }
    }
    public override TypeDefinition Resolve(TypeReference type)
    {
        try { return base.Resolve(type); }
        catch (AssemblyResolutionException) when (enums.ContainsKey(type.FullName))
        { return enums[type.FullName]; }
    }
}
