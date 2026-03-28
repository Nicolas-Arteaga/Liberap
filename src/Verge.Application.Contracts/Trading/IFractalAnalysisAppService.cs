using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading;

public interface IFractalAnalysisAppService : IApplicationService
{
    Task<FractalStatusDto> GetStatusAsync(string symbol);
}

public class FractalStatusDto
{
    public string Symbol { get; set; }
    public decimal LastPrice { get; set; }
    public bool IsAccumulating { get; set; }
    public double StabilityRange { get; set; }
    public string PatternName { get; set; }
}
