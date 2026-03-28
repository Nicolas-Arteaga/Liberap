using System.Collections.Generic;
using System.Threading.Tasks;

namespace Verge.Trading;

public interface IFractalPatternManager
{
    Task ProcessPriceAsync(string symbol, decimal price);
}
