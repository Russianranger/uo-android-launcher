using Mono.Cecil;

internal static class ResourceCpuPolicy
{
    internal static void Verify(string file)
    {
        using var helper = ModuleDefinition.ReadModule(file);
        var methods = helper.GetTypes().SelectMany(t => t.Methods).ToDictionary(m => m.FullName);
        var roots = helper.GetTypes().Where(t => t.FullName == "Memento.ResourceTrace" || t.FullName.StartsWith("Memento.ResourceTrace/") ||
                t.FullName == "Memento.ChunkTrace" || t.FullName.StartsWith("Memento.ChunkTrace/"))
            .SelectMany(t => t.Methods).ToArray();
        if (!helper.GetTypes().Any(t => t.FullName == "Memento.ChunkTrace")) throw new Exception("Focused chunk observations are missing");
        var queue = new Queue<MethodDefinition>(roots); var visited = new HashSet<string>();
        var forbidden = new HashSet<string> { "ThreadCpu", "GetThreadTimes", "Clock", "clock_gettime", "QueryThreadCycleTime", "NtQueryInformationThread" };
        while (queue.Count != 0)
        {
            var method = queue.Dequeue();
            if (!visited.Add(method.FullName)) continue;
            if (method.HasPInvokeInfo && forbidden.Contains(method.PInvokeInfo.EntryPoint))
                throw new Exception("A resource observation can import CPU: " + method.FullName + " -> " + method.PInvokeInfo.EntryPoint);
            if (!method.HasBody) continue;
            foreach (var call in method.Body.Instructions.Select(i => i.Operand).OfType<MethodReference>())
            {
                if (forbidden.Contains(call.Name)) throw new Exception("A resource observation can query CPU: " + method.FullName + " -> " + call.FullName);
                if (methods.TryGetValue(call.FullName, out var target)) queue.Enqueue(target);
            }
        }
        var cold = helper.GetType("Memento.ColdTrace");
        if (!cold.Methods.Any(m => m.Name == "ThreadCpu") || !cold.Methods.Any(m => m.Name == "GetThreadTimes") ||
            !cold.Methods.Where(m => m.Name is "BeginStage" or "EndStage").All(m => m.Body.Instructions.Any(i => i.Operand is MethodReference call && call.Name == "ThreadCpu")))
            throw new Exception("Existing frame/EndDraw CPU diagnostics were not preserved");
        Console.WriteLine("RESOURCE_CPU_QUERY_POLICY_OK resource_cpu_calls=0 preserved_frame_cpu=true reachable_methods=" + visited.Count);
    }
}
